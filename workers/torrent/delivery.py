"""Publish verified bytes to the Windows operator's real Downloads folder.

The service retains its resumable originals. A completed publication is an atomic,
hash-checked copy, never a move or a permission grant over the private journal.
Only the authenticated native host can register an output root.
"""

import hashlib
import json
import os
import stat
import time
import uuid
from pathlib import Path

from storage import Problem, io_path, packed, require, safe_file


def plain_path(path):
    path = Path(path)
    require(path.is_absolute(), 409, "The delivery destination must be absolute.")
    require(".." not in path.parts, 409, "A delivery path cannot traverse its parent.")
    if os.name == "nt":
        # The service can open the registered account directory by its full name;
        # it cannot inspect the user's Downloads or even its Torrenter parent.
        # Windows resolves the existing leaf by handle. Compare that final path
        # before creating anything; a junction in a parent must not redirect it.
        probe = path
        while True:
            try:
                resolved = probe.resolve(strict=True)
                info = probe.lstat()
                break
            except FileNotFoundError:
                # Only the job directory may be new; its account root must exist.
                if probe != path or probe.parent == probe:
                    raise
                probe = probe.parent
        require(resolved == probe and not info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                409, "Delivery path contains a reparse point.")
        return path
    for item in [path, *path.parents]:
        if os.path.lexists(item):
            info = item.lstat()
            require(not item.is_symlink() and not getattr(info, "st_file_attributes", 0)
                    & stat.FILE_ATTRIBUTE_REPARSE_POINT, 409, "Delivery path contains a reparse point.")
    return path


def fingerprint(path):
    info = io_path(path).stat()
    return [info.st_size, info.st_mtime_ns, info.st_ino]


def copy_verified(source, destination, entries, closing):
    """Never overwrite a file the user changed; retry/crash recovery reuses exact bytes."""
    root = plain_path(destination)
    root.mkdir(parents=True, exist_ok=True)
    result = []
    for entry in entries:
        if closing.is_set():
            raise InterruptedError("Delivery interrupted; it will resume after restart.")
        origin = io_path(safe_file(source, entry["path"]))
        target = safe_file(root, entry["path"])
        output = io_path(target)  # long-path form for I/O; messages keep the plain name
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            with output.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            require(actual == entry["sha256"] and output.stat().st_size == entry["size"],
                    409, "An existing Downloads file differs; it has been preserved: " + str(target))
        else:
            temporary = output.with_name(".torrenter-" + uuid.uuid4().hex + ".part")
            try:
                sha = hashlib.sha256()
                length = 0
                with origin.open("rb") as src, temporary.open("xb") as out:
                    while block := src.read(1024 * 1024):
                        if closing.is_set():
                            raise InterruptedError("Delivery interrupted; it will resume after restart.")
                        out.write(block)
                        length += len(block)
                        sha.update(block)
                    out.flush()
                    os.fsync(out.fileno())
                require(length == entry["size"] and sha.hexdigest() == entry["sha256"],
                        409, "The service file changed before delivery: " + entry["path"])
                # A no-replace publication. A concurrent user-created file wins.
                if os.name == "nt":
                    os.rename(temporary, output)  # Windows refuses an existing target.
                else:
                    os.link(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        result.append({**entry, "fingerprint": fingerprint(target)})
    return result


def publish(source, primary, fallback, primary_error, fallback_error, entries, closing):
    """Account roots come exclusively from the authenticated native control pipe."""
    if primary and not primary_error:
        try:
            return primary, "downloads", None, copy_verified(source, primary, entries, closing)
        except InterruptedError:
            raise
        except OSError as exc:
            primary_error = str(exc)
    if not fallback:
        raise OSError("Windows Downloads: " + str(primary_error) +
                      ("; content_generated: " + fallback_error if fallback_error else ""))
    try:
        return fallback, "content_generated", primary_error, copy_verified(source, fallback, entries, closing)
    except InterruptedError:
        raise
    except (OSError, Problem) as exc:
        raise OSError(f"Windows Downloads: {primary_error}; content_generated: {exc}") from exc


class Delivery:
    def __init__(self, journal, executor, closing):
        self.j, self.executor, self.closing = journal, executor, closing
        self.pending = {}
        self.retry_after = {}

    def roots(self, row):
        def target(table):
            root = self.j.db.execute("SELECT path,error FROM " + table + " WHERE owner=?", (row["owner"],)).fetchone()
            return (str(Path(root["path"]) / row["id"]) if root and root["path"] else None,
                    root["error"] if root else None)

        return (*target("delivery_roots"), *target("fallback_roots"))

    def status(self, row):
        primary, first_error, fallback, second_error = self.roots(row)
        if not any((primary, first_error, fallback, second_error)):
            return {"delivery_state": "service_store", "saved_to": None, "delivery_error": None}
        saved_to = primary or fallback
        answer = {"delivery_state": "pending", "saved_to": saved_to, "delivery_error": None,
                  "delivery_location": "downloads" if primary else "content_generated", "downloads_error": first_error}
        if not row["completed"]:
            return answer
        saved = self.j.db.execute("SELECT * FROM deliveries WHERE job=?", (row["id"],)).fetchone()
        if saved and saved["revision"] == row["revision"]:
            if saved["error"]:
                return {**answer, "delivery_state": "failed", "delivery_error": saved["error"]}
            saved_to = saved["path"]
            location = self.j.db.execute("SELECT kind,primary_error FROM delivery_locations WHERE job=?",
                                         (row["id"],)).fetchone()
            answer.update(saved_to=saved_to, delivery_location=location["kind"] if location else "downloads",
                          downloads_error=location["primary_error"] if location else None)
            try:
                plain_path(saved_to)
                for entry in json.loads(saved["files"]):
                    require(fingerprint(safe_file(saved_to, entry["path"])) == entry["fingerprint"],
                            409, "A delivered file was changed or removed.")
            except (OSError, Problem) as exc:
                return {**answer, "delivery_state": "failed", "delivery_error": str(exc)}
            return {**answer, "delivery_state": "saved"}
        if not saved_to:
            return {**answer, "delivery_state": "failed",
                    "delivery_error": "; ".join(filter(None, (first_error, second_error)))}
        return answer

    def tick(self, rows):
        now = time.monotonic()
        live = {row["id"] for row in rows}
        for ident, (_, _, future) in list(self.pending.items()):
            if ident not in live and (future.done() or future.cancel()):
                del self.pending[ident]
        for row in rows:
            ident = row["id"]
            current = self.status(row)
            if ident in self.pending:
                revision, roots, future = self.pending[ident]
                if not future.done():
                    continue
                del self.pending[ident]
                if revision != row["revision"] or roots != self.roots(row):
                    continue
                try:
                    destination, kind, primary_error, entries = future.result()
                    error = None
                except (OSError, Problem) as exc:
                    destination, kind, primary_error, entries, error = current["saved_to"], None, None, [], str(exc)
                self.j.db.execute("INSERT OR REPLACE INTO deliveries VALUES(?,?,?,?,?)",
                                  (ident, revision, destination, packed(entries), error))
                self.j.db.execute("INSERT OR REPLACE INTO delivery_locations VALUES(?,?,?)",
                                  (ident, kind, primary_error))
                self.j.event(row["owner"], ident, "delivery_failed" if error else "saved_to_" + kind)
                self.retry_after[ident] = now + 60
                continue
            if (not row["completed"] or current["delivery_state"] in ("saved", "service_store")
                    or not current["saved_to"] or now < self.retry_after.get(ident, 0)
                    or len(self.pending) >= 2):
                continue
            previous = self.j.db.execute("SELECT revision,path,error FROM deliveries WHERE job=?", (ident,)).fetchone()
            if (previous and previous["revision"] == row["revision"]
                    and not previous["error"]):
                # A user may move/delete/edit a delivered copy in Explorer. Report
                # that change; do not silently recreate it on every polling tick.
                continue
            published = self.j.db.execute("SELECT manifest FROM published WHERE job=?", (ident,)).fetchone()
            if published:
                roots = self.roots(row)
                primary, first_error, fallback, second_error = roots
                self.pending[ident] = (row["revision"], roots, self.executor.submit(
                    publish, self.j.files_root(row), primary, fallback, first_error, second_error,
                    json.loads(published[0]), self.closing))
