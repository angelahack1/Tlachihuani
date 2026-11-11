"""BitTorrent engine. Destination paths and peer policy are service decisions."""

import hashlib
import ipaddress
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import re
import time
from pathlib import PureWindowsPath
from urllib.parse import urlsplit

import libtorrent as lt

from storage import Problem, io_path, packed, require, safe_file
from delivery import Delivery


def inspect(raw):
    require(0 < len(raw) <= 1048576, 413, "Metainfo exceeds the configured limit.")

    def component(value):
        require(isinstance(value, bytes), 422, "Invalid file name encoding.")
        try:
            part = value.decode("utf-8")
        except UnicodeError:
            raise Problem(422, "File names must be UTF-8.") from None
        require(
            part not in ("", ".", "..")
            and not any(c in part for c in '<>:"/\\|?*')
            and all(ord(c) >= 32 for c in part)
            and not part.endswith((" ", "."))
            and not PureWindowsPath(part).is_reserved(),
            422,
            "Unsafe metainfo path component.",
        )

    try:
        meta = lt.bdecode(raw)[b"info"]
        component(meta[b"name"])
        if b"name.utf-8" in meta:
            component(meta[b"name.utf-8"])
        for entry in meta.get(b"files", []):
            require(
                b"symlink path" not in entry, 422, "Torrent symlinks are unsupported."
            )
            for key in (b"path", b"path.utf-8"):
                for part in entry.get(key, []):
                    component(part)

        def walk(tree, depth):
            require(
                isinstance(tree, dict) and depth <= 64, 422, "Invalid v2 file tree."
            )
            for name, children in tree.items():
                if name:
                    component(name)
                    walk(children, depth + 1)
                else:
                    require(
                        b"symlink path" not in children,
                        422,
                        "Torrent symlinks are unsupported.",
                    )

        if b"file tree" in meta:
            walk(meta[b"file tree"], 0)
        info = lt.torrent_info(raw)
    except (RuntimeError, ValueError, KeyError, TypeError):
        raise Problem(422, "Invalid torrent metainfo.") from None
    fs = info.files()
    require(
        0 < fs.num_files() <= 4096 and info.total_size() <= 50 * 1024**3,
        422,
        "Torrent exceeds size or file limits.",
    )
    seen = set()
    files = []
    for i in range(fs.num_files()):
        path = fs.file_path(i).replace("\\", "/")
        require(
            not fs.file_flags(i) & fs.flag_symlink,
            422,
            "Torrent symlinks are unsupported.",
        )
        if fs.file_flags(i) & fs.flag_pad_file:
            continue
        parts = path.split("/")
        require(
            len(path) <= 800
            and all(
                part not in ("", ".", "..")
                and not re.search(r'[<>:"|?*\x00-\x1f]', part)
                and not part.endswith((" ", "."))
                and not PureWindowsPath(part).is_reserved()
                for part in parts
            ),
            422,
            "Unsafe torrent path.",
        )
        require(path.casefold() not in seen, 422, "Duplicate torrent file name.")
        require(
            not any(
                prefix.casefold() in seen
                for prefix in ["/".join(parts[:i]) for i in range(1, len(parts))]
            ),
            422,
            "File collides with a directory.",
        )
        seen.add(path.casefold())
        files.append({"id": i, "path": path, "size": fs.file_size(i)})
    require(files, 422, "No selectable files.")
    for path in seen:
        require(
            not any(
                "/".join(path.split("/")[:i]) in seen
                for i in range(1, path.count("/") + 1)
            ),
            422,
            "File collides with a directory.",
        )
    return info, files


def endpoint(url):
    u = urlsplit(url)
    require(
        u.scheme in ("http", "https", "udp")
        and u.hostname
        and not u.username
        and not u.password,
        422,
        "Unsupported tracker or web seed.",
    )
    return u.hostname


class Engine:
    # A silent swarm must not indefinitely occupy another download's slot.
    # These timers are runtime scheduling state, never a change to user intent.
    STALL_SECONDS = 180
    RETRY_SECONDS = 60
    DISK_SETTLE_SECONDS = 60

    def __init__(self, journal, development):
        self.j = journal
        self.development = development
        self.sessions = {}
        self.handles = {}
        self.lookups = {}
        self.timed_out_owners = set()
        self.last_checkpoint = 0
        self.last_cleanup = 0
        self.pending_release = {}
        self.failures = {}
        self.progress = {}
        self.retry_after = {}
        self.queue_turn = {}
        self.verification_wait = {}
        self.disk_quiet = set()
        self.publisher = ThreadPoolExecutor(
            max_workers=2, thread_name_prefix="verify-selected"
        )
        self.publications = {}
        self.closing = threading.Event()
        self.delivery = Delivery(journal, self.publisher, self.closing)

    def verify_files(self, root, metainfo, selected):
        _, files = inspect(metainfo)
        entries = []
        for file in files:
            if file["id"] not in selected:
                continue
            path = io_path(safe_file(root, file["path"]))
            before = path.stat()
            require(before.st_size == file["size"], 409, "Selected file is incomplete.")
            sha = hashlib.sha256()
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    if self.closing.is_set():
                        raise InterruptedError("Publication interrupted.")
                    sha.update(block)
            after = path.stat()
            require(
                (after.st_size, after.st_mtime_ns, after.st_ino)
                == (before.st_size, before.st_mtime_ns, before.st_ino),
                409,
                "File changed during verification.",
            )
            entries.append(dict(file, sha256=sha.hexdigest()))
        return entries

    @staticmethod
    def session_settings(development):
        # An installed engine must be reachable by peers: without router port
        # mapping (UPnP / NAT-PMP) and incoming uTP, a swarm whose seeds are
        # behind NAT never connects and the download stalls at 0 B/s.
        # Development fixtures stay loopback-only and never touch the router.
        public = not development
        return {
            "listen_interfaces": "0.0.0.0:0" if public else "127.0.0.1:0",
            "enable_dht": public,
            "enable_lsd": False,
            "enable_upnp": public,
            "enable_natpmp": public,
            "allow_multiple_connections_per_ip": development,
            "ssrf_mitigation": True,
            "enable_incoming_utp": public,
            "apply_ip_filter_to_trackers": True,
            "upload_rate_limit": 262144,
            "alert_mask": int(
                lt.alert.category_t.storage_notification
                | lt.alert.category_t.error_notification
                | lt.alert.category_t.status_notification
            ),
        }

    def session(self, owner):
        if owner in self.sessions:
            return self.sessions[owner]
        session = lt.session(self.session_settings(self.development))
        blocked = [
            "0.0.0.0/8",
            "10.0.0.0/8",
            "100.64.0.0/10",
            "127.0.0.0/8",
            "169.254.0.0/16",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "224.0.0.0/4",
            "240.0.0.0/4",
            "::/96",
            "::ffff:0:0/96",
            "fc00::/7",
            "fe80::/10",
            "ff00::/8",
        ]
        rule = lt.ip_filter()
        for network in blocked:
            n = ipaddress.ip_network(network)
            rule.add_rule(str(n.network_address), str(n.broadcast_address), 1)
        if self.development:
            # Isolated console fixtures use loopback exclusively, never a public swarm.
            rule.add_rule("0.0.0.0", "255.255.255.255", 1)
            rule.add_rule("::", "ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff", 1)
            rule.add_rule("127.0.0.1", "127.0.0.1", 0)
        session.set_ip_filter(rule)
        self.sessions[owner] = session
        return session

    @staticmethod
    def magnet_parameters(uri):
        require(
            isinstance(uri, str) and uri.startswith("magnet:?") and len(uri) <= 8192,
            422,
            "Expected a bounded magnet URI.",
        )
        try:
            params = lt.parse_magnet_uri(uri)
        except RuntimeError:
            raise Problem(422, "Invalid magnet.") from None
        for tracker in params.trackers:
            endpoint(tracker)
        for url in [*params.url_seeds, *params.http_seeds]:
            endpoint(url)
            require(
                urlsplit(url).scheme in ("http", "https"),
                422,
                "Invalid magnet web seed.",
            )
        return params

    def start_lookup(self, owner, ident, uri):
        params = self.magnet_parameters(uri)
        params.save_path = str(self.j.root / "inspections" / ident)
        params.flags |= (
            lt.torrent_flags.upload_mode
            | lt.torrent_flags.default_dont_download
            | lt.torrent_flags.duplicate_is_error
        )
        params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
        self.lookups[ident] = (
            owner,
            self.session(owner).add_torrent(params),
            time.monotonic() + 180,
        )

    def fill_lookup_slots(self):
        """The four oldest pending admissions own the four metadata slots."""
        if len(self.lookups) >= 4:
            return
        rows = self.j.db.execute(
            "SELECT id,owner,magnet FROM inspections WHERE pending=1 ORDER BY rowid LIMIT 4"
        ).fetchall()
        for row in rows:
            if row["id"] in self.lookups:
                continue
            try:
                self.start_lookup(row["owner"], row["id"], row["magnet"])
            except (Problem, RuntimeError, ValueError):
                # A rejected handle must never block later magnets in the queue.
                self.finish_lookup(row["id"], None)

    def finish_lookup(self, ident, metainfo):
        self.j.db.execute(
            "UPDATE inspections SET pending=0,metainfo=?,expires=? WHERE id=?",
            (metainfo, int(time.time()) + 900, ident),
        )

    def retire_timed_out_sessions(self):
        # libtorrent keeps peer failures and backoff in its session. A timed-out
        # account must get a fresh discovery session on its next attempt, but
        # never tear down a session that still owns a live transfer or lookup.
        if not self.timed_out_owners:
            return
        busy = {owner for owner, _, _ in self.lookups.values()}
        if self.handles:
            slots = ",".join("?" for _ in self.handles)
            busy.update(row["owner"] for row in self.j.db.execute(
                f"SELECT DISTINCT owner FROM jobs WHERE id IN ({slots})", tuple(self.handles)
            ))
        for owner in self.timed_out_owners - busy:
            self.sessions.pop(owner, None)
            self.timed_out_owners.discard(owner)

    def open(self, row):
        info, files = inspect(row["metainfo"])
        root = self.j.files_root(row)
        root.mkdir(parents=True, exist_ok=True)
        for file in files:
            safe_file(root, file["path"])
        selected = set(json.loads(row["selection"]))
        params = lt.add_torrent_params()
        if row["resume"]:
            try:
                params = lt.read_resume_data(row["resume"])
            except RuntimeError:
                pass  # existing pieces will be checked
        params.ti = info
        params.save_path = str(root)
        opts = json.loads(row["options"])
        if opts.get("bootstrap_magnet"):
            params.peers = lt.parse_magnet_uri(opts["bootstrap_magnet"]).peers
        priorities = opts.get("priorities", {})
        params.file_priorities = [
            priorities.get(str(i), 4) if i in selected else 0
            for i in range(info.num_files())
        ]
        if "trackers" in opts:
            params.trackers = opts["trackers"]
            params.tracker_tiers = list(range(len(params.trackers)))
            params.flags |= lt.torrent_flags.override_trackers
        if "web_seeds" in opts:
            params.url_seeds = opts["web_seeds"]
            params.http_seeds = []
            params.flags |= lt.torrent_flags.override_web_seeds
        params.flags &= ~(
            lt.torrent_flags.paused
            | lt.torrent_flags.auto_managed
            | lt.torrent_flags.seed_mode
            | lt.torrent_flags.upload_mode
        )
        params.flags |= (
            lt.torrent_flags.duplicate_is_error | lt.torrent_flags.apply_ip_filter
        )
        if info.priv():
            params.flags |= (
                lt.torrent_flags.disable_dht
                | lt.torrent_flags.disable_lsd
                | lt.torrent_flags.disable_pex
            )
        h = self.session(row["owner"]).add_torrent(params)
        h.set_download_limit(opts.get("download_limit", 0))
        h.set_upload_limit(opts.get("upload_limit", 0))
        self.handles[row["id"]] = h
        self.retry_after.pop(row["id"], None)
        self.progress[row["id"]] = (0, time.monotonic())
        return h

    def rotate_stalled(self, rows):
        """Yield only to runnable work; keep partial data and stopped jobs untouched."""
        now = time.monotonic()
        counts = {}
        for row in rows:
            if row["id"] in self.handles:
                counts[row["owner"]] = counts.get(row["owner"], 0) + 1
        waiting = [row for row in rows if row["desired"] == "running"
                   and not row["completed"] and row["id"] not in self.handles
                   and row["id"] not in self.failures
                   and self.retry_after.get(row["id"], 0) <= now]
        for row in rows:
            ident = row["id"]
            h = self.handles.get(ident)
            if not h or ident in self.pending_release or row["desired"] != "running":
                continue
            status = h.status()
            if row["completed"] or status.is_finished or "checking" in str(status.state) or status.errc.value():
                self.progress[ident] = (status.total_payload_download, now)
                continue
            previous, since = self.progress.get(ident, (status.total_payload_download, now))
            if status.total_payload_download != previous or status.download_payload_rate > 0:
                since = now
            self.progress[ident] = (status.total_payload_download, since)
            # Reserve each released slot for distinct queued work. A queued job
            # belonging to another saturated account cannot use this slot.
            candidate = next((r for r in waiting if
                              (r["owner"] == row["owner"] and counts[r["owner"]] >= 2)
                              or (len(self.handles) >= 4 and
                                  (r["owner"] == row["owner"] or counts.get(r["owner"], 0) < 2))), None)
            if now - since < self.STALL_SECONDS or candidate is None:
                continue
            waiting.remove(candidate)
            counts[row["owner"]] -= 1
            counts[candidate["owner"]] = counts.get(candidate["owner"], 0) + 1
            self.retry_after[ident] = now + self.RETRY_SECONDS
            self.queue_turn[ident] = now
            h.pause()
            h.save_resume_data()
            self.pending_release[ident] = time.time()
            self.j.event(row["owner"], ident, "stalled_retry")

    def forget_handle(self, ident):
        self.progress.pop(ident, None)
        self.verification_wait.pop(ident, None)
        self.disk_quiet.discard(ident)

    def verify_ready(self, row, handle):
        """pause() is asynchronous: hash only after its disk-complete alert."""
        ident = row["id"]
        if ident in self.publications:
            return
        now = time.monotonic()
        waiting = self.verification_wait.get(ident)
        if waiting is None:
            self.verification_wait[ident] = (row["revision"], now)
            self.disk_quiet.discard(ident)
            handle.pause()
            return
        # A label/revision edit does not resume the disk writer. Keep its pause
        # acknowledgement; pause() on an already paused handle emits no new one.
        if waiting[0] != row["revision"]:
            self.verification_wait[ident] = (row["revision"], waiting[1])
        if ident in self.disk_quiet:
            self.publications[ident] = (
                row["revision"], self.publisher.submit(
                    self.verify_files, self.j.files_root(row), row["metainfo"],
                    json.loads(row["selection"])),
            )
        elif now - waiting[1] > self.DISK_SETTLE_SECONDS:
            self.failures[ident] = "Disk did not finish pausing for verification. Recheck this download."

    def alerts(self):
        for session in self.sessions.values():
            for alert in session.pop_alerts():
                if isinstance(alert, lt.torrent_paused_alert):
                    for ident, handle in self.handles.items():
                        if handle == alert.handle and ident in self.verification_wait:
                            self.disk_quiet.add(ident)
                if isinstance(
                    alert, (lt.save_resume_data_alert, lt.save_resume_data_failed_alert)
                ):
                    ident = next(
                        (i for i, h in self.handles.items() if h == alert.handle), None
                    )
                    if ident:
                        if isinstance(alert, lt.save_resume_data_alert):
                            self.j.db.execute(
                                "UPDATE jobs SET resume=? WHERE id=?",
                                (bytes(lt.write_resume_data_buf(alert.params)), ident),
                            )
                        if ident in self.pending_release:
                            # Missing resume data is recoverable by rechecking existing bytes.
                            session.remove_torrent(self.handles.pop(ident))
                            self.pending_release.pop(ident, None)
                            self.forget_handle(ident)

    def snapshot(self, row):
        result = json.loads(row["snapshot"])
        # Stored snapshots are historical evidence, not current error state.
        for key in ("error", "queue_reason", "retry_in_seconds"):
            result.pop(key, None)
        desired = row["desired"]
        h = self.handles.get(row["id"])
        if h and h.is_valid():
            s = h.status()
            phase = "downloading" if s.num_peers else "waiting_for_peers"
            if "checking" in str(s.state):
                phase = "checking"
            elif s.errc.value():
                phase = "failed"
                result["error"] = s.errc.message()
            elif s.is_finished:
                phase = (
                    "seeding"
                    if row["completed"]
                    and json.loads(row["options"]).get("seed_after_completion")
                    else ("completed" if row["completed"] else "verifying")
                )
            if row["id"] in self.failures and not row["completed"]:
                phase = "failed"
            if desired != "running":
                phase = {
                    "paused": "pausing",
                    "stopped": "stopping",
                    "cancelled": "cancelling",
                }[desired]
            result.update(
                phase=phase,
                verified_bytes=s.total_wanted_done,
                download_rate_bps=s.download_payload_rate,
                upload_rate_bps=s.upload_payload_rate,
                peers=s.num_peers,
                seeds=s.num_seeds,
                availability=s.distributed_copies
                if s.distributed_copies >= 0
                else None,
                known_seeds=s.num_complete if s.num_complete >= 0 else None,
                known_peers=s.num_incomplete if s.num_incomplete >= 0 else None,
                eta_seconds=int(
                    max(0, s.total_wanted - s.total_wanted_done)
                    / s.download_payload_rate
                )
                if s.download_payload_rate
                else None,
                ratio=s.all_time_upload / max(s.all_time_download, 1),
            )
        else:
            result.update(
                phase="completed" if row["completed"] else {
                    "paused": "paused",
                    "stopped": "stopped",
                    "cancelled": "cancelled",
                }.get(
                    desired,
                    "completed"
                    if row["completed"]
                    else ("failed" if row["id"] in self.failures else "queued"),
                ),
                download_rate_bps=0,
                upload_rate_bps=0,
                peers=0,
                seeds=0,
            )
        result.update(
            job_id=row["id"],
            revision=row["revision"],
            desired_state=desired,
            completed_at=row["completed"],
            **json.loads(row["options"]),
        )
        for private_setting in ("trackers", "web_seeds", "bootstrap_magnet"):
            result.pop(private_setting, None)
        result["destination_root_id"] = row["root_id"]
        result.update(self.delivery.status(row))
        if row["id"] in self.failures and not row["completed"]:
            result["error"] = self.failures[row["id"]]
        if row["id"] in self.retry_after and desired == "running" and not row["completed"]:
            result.update(phase="queued", queue_reason="stalled_retry",
                          retry_in_seconds=max(0, int(self.retry_after[row["id"]] - time.monotonic())),
                          download_rate_bps=0, upload_rate_bps=0, peers=0, seeds=0)
        return result

    def tick(self):
        now = time.time()
        self.alerts()
        for ident, (owner, h, expires) in list(self.lookups.items()):
            has_metadata = h.status().has_metadata
            if has_metadata or time.monotonic() >= expires:
                if has_metadata:
                    self.timed_out_owners.discard(owner)
                else:
                    self.timed_out_owners.add(owner)
                reviewed = None
                try:
                    if has_metadata:
                        # Peers send the info dictionary only. The reviewed admission must
                        # carry its approved discovery hints into the fresh download handle.
                        uri = self.j.db.execute(
                            "SELECT magnet FROM inspections WHERE id=?", (ident,)
                        ).fetchone()[0]
                        hints = lt.parse_magnet_uri(uri)
                        creator = lt.create_torrent(h.torrent_file())
                        for index, url in enumerate(hints.trackers):
                            creator.add_tracker(
                                url,
                                hints.tracker_tiers[index]
                                if index < len(hints.tracker_tiers)
                                else 0,
                            )
                        for url in hints.url_seeds:
                            creator.add_url_seed(url)
                        for url in hints.http_seeds:
                            creator.add_http_seed(url)
                        raw = bytes(lt.bencode(creator.generate()))
                        inspect(raw)
                        reviewed = raw
                except (Problem, RuntimeError, ValueError, KeyError):
                    pass  # Invalid remote metadata expires this inspection; other jobs continue.
                finally:
                    self.finish_lookup(ident, reviewed)
                    self.sessions[owner].remove_torrent(h)
                    del self.lookups[ident]
        self.retire_timed_out_sessions()
        self.fill_lookup_slots()
        rows = self.j.db.execute(
            "SELECT * FROM jobs WHERE removed=0 ORDER BY coalesce(json_extract(options,'$.queue_position'),0),created,id"
        ).fetchall()
        live_ids = {row["id"] for row in rows}
        for mapping in (self.progress, self.retry_after, self.queue_turn):
            for ident in set(mapping) - live_ids:
                del mapping[ident]
        self.rotate_stalled(rows)
        # Stable sort retains the user's queue order among jobs on the same turn.
        rows.sort(key=lambda row: self.queue_turn.get(row["id"], 0))
        self.delivery.tick(rows)
        for row in rows:
            ident = row["id"]
            h = self.handles.get(ident)
            opts = json.loads(row["options"])
            can_seed = (
                row["completed"]
                and opts.get("seed_after_completion")
                and now < opts.get("seed_until", row["completed"] + 3600)
                and not opts.get("seed_finished")
            )
            if (
                row["desired"] == "running"
                and (not row["completed"] or can_seed)
                and not h
                and ident not in self.failures
                and self.retry_after.get(ident, 0) <= time.monotonic()
                and len(self.handles) < 4
            ):
                same_owner = sum(
                    r["id"] in self.handles and r["owner"] == row["owner"] for r in rows
                )
                if same_owner < 2:
                    try:
                        h = self.open(row)
                    except (RuntimeError, OSError, ValueError, Problem) as exc:
                        self.failures[ident] = str(exc)
            if not h:
                continue
            state = self.snapshot(row)
            before = json.loads(row["snapshot"])
            if before != state:
                self.j.db.execute(
                    "UPDATE jobs SET snapshot=? WHERE id=?", (packed(state), ident)
                )
                if before.get("phase") != state["phase"]:
                    self.j.event(row["owner"], ident, state["phase"])
            if state["phase"] == "verifying":
                self.verify_ready(row, h)
            if ident in self.publications and self.publications[ident][1].done():
                revision, future = self.publications.pop(ident)
                if revision == row["revision"] and row["desired"] == "running":
                    try:
                        entries = future.result()
                    except (OSError, Problem, RuntimeError) as exc:
                        self.failures[ident] = str(exc)
                    else:
                        self.failures.pop(ident, None)
                        self.j.db.execute(
                            "INSERT OR REPLACE INTO published VALUES(?,?)",
                            (ident, packed(entries)),
                        )
                        self.verification_wait.pop(ident, None)
                        self.disk_quiet.discard(ident)
                        if opts.get("seed_after_completion"):
                            h.resume()
                        self.j.db.execute(
                            "UPDATE jobs SET completed=? WHERE id=?", (int(now), ident)
                        )
            ratio_reached = state["phase"] == "seeding" and (
                now >= opts.get("seed_until", row["completed"] + 3600)
                or h.status().all_time_upload >= state["selected_bytes"]
            )
            if ratio_reached:
                opts["seed_finished"] = True
                self.j.db.execute(
                    "UPDATE jobs SET options=? WHERE id=?", (packed(opts), ident)
                )
            if (
                row["desired"] != "running"
                or ident in self.pending_release
                or state["phase"] in ("completed", "failed")
                or ratio_reached
            ):
                if ident not in self.pending_release:
                    h.pause()
                    h.save_resume_data()
                    self.pending_release[ident] = now
                elif now - self.pending_release[ident] > 12:
                    self.sessions[row["owner"]].remove_torrent(self.handles.pop(ident))
                    del self.pending_release[ident]
                    self.forget_handle(ident)
            elif now - self.last_checkpoint >= 30:
                h.save_resume_data()
        if now - self.last_checkpoint >= 30:
            self.last_checkpoint = now
        if now - self.last_cleanup >= 60:
            self.j.db.execute("DELETE FROM inspections WHERE pending=0 AND expires<?", (int(now),))
            self.j.db.execute("DELETE FROM tokens WHERE expires<?", (int(now),))
            self.j.db.execute("DELETE FROM previews WHERE expires<?", (int(now),))
            self.j.db.execute("DELETE FROM nonces WHERE expires<?", (int(now),))
            for old in self.j.db.execute(
                "SELECT owner,max(cursor) AS last FROM events WHERE at<? GROUP BY owner",
                (int(now) - 604800,),
            ).fetchall():
                self.j.db.execute(
                    "INSERT OR REPLACE INTO event_floors VALUES(?,?)",
                    (old["owner"], old["last"]),
                )
            self.j.db.execute("DELETE FROM events WHERE at<?", (int(now) - 604800,))
            self.last_cleanup = now

    def close(self):
        self.closing.set()
        self.publisher.shutdown(wait=True, cancel_futures=True)
        for h in self.handles.values():
            h.pause()
            h.save_resume_data()
        until = time.monotonic() + 1
        while self.handles and time.monotonic() < until:
            time.sleep(0.05)
            self.alerts()
        self.j.db.commit()
