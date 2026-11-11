"""Closed REST dispatch. The Windows host reserves native operations for its ACL-protected pipe."""

import base64
import hashlib
import hmac
import json
import secrets
import shutil
import time
from urllib.parse import urlsplit

from engine import endpoint, inspect
from delivery import plain_path
import libtorrent as lt
from storage import Problem, digest, io_path, new_id, packed, require, safe_file

SCOPES = "read submit control remove erase"


class Api:
    def __init__(self, journal, engine):
        self.j, self.e = journal, engine

    def native(self, req):
        op, owner = req["op"], req["owner"]
        if op == "impact":
            total = self.j.db.execute(
                "SELECT count(*) FROM jobs WHERE removed=0"
            ).fetchone()[0]
            return {"records": total, "active": len(self.e.handles)}
        if op == "issue":
            profile = req.get("profile", "")
            require(
                isinstance(profile, str) and len(profile) <= 128,
                400,
                "Invalid profile.",
            )
            account = owner if not profile else owner + "/" + digest(profile)
            if "delivery_root" in req or "delivery_error" in req:
                # Only JobsHost's authenticated and validated native channel supplies
                # this destination. REST clients cannot choose host filesystem paths.
                self.j.db.execute(
                    "INSERT OR REPLACE INTO delivery_roots VALUES(?,?,?)",
                    (account, req.get("delivery_root"), req.get("delivery_error")),
                )
            if "fallback_root" in req or "fallback_error" in req:
                self.j.db.execute("INSERT OR REPLACE INTO fallback_roots VALUES(?,?,?)",
                                  (account, req.get("fallback_root"), req.get("fallback_error")))
            scope = req.get("scope", "read")
            require(
                isinstance(scope, str) and set(scope.split()) <= set(SCOPES.split()),
                400,
                "Unknown scope.",
            )
            if req.get("gateway"):
                key, secret = new_id(), secrets.token_urlsafe(48)
                self.j.db.execute(
                    "INSERT INTO gateways(id,owner,account,secret,scope) VALUES(?,?,?,?,?)",
                    (key, account, profile, secret, scope),
                )
                return {"gateway_id": key, "signing_key": secret, "account": profile}
            return self.j.issue(account, scope, 3600)
        if op == "revoke":
            self.j.db.execute(
                "DELETE FROM tokens WHERE owner=? OR owner LIKE ?",
                (owner, owner + "/%"),
            )
            self.j.db.execute(
                "DELETE FROM gateways WHERE owner=? OR owner LIKE ?",
                (owner, owner + "/%"),
            )
            return {"revoked": True}
        if op == "pending-deletions":
            rows = self.j.db.execute(
                "SELECT id,job FROM previews WHERE (owner=? OR owner LIKE ?) AND approved=0 AND expires>? ORDER BY expires LIMIT 16",
                (owner, owner + "/%", time.time()),
            ).fetchall()
            return {
                "items": [{"preview_id": r["id"], "job_id": r["job"]} for r in rows]
            }
        if op == "deletion-details":
            row = self.j.db.execute(
                "SELECT * FROM previews WHERE id=? AND expires>?",
                (req.get("preview_id"), time.time()),
            ).fetchone()
            require(
                row and (row["owner"] == owner or row["owner"].startswith(owner + "/")),
                404,
                "No pending preview.",
            )
            return {
                "job_id": row["job"],
                "manifest_digest": digest(row["manifest"]),
                "files": json.loads(row["manifest"]),
            }
        if op == "approve-delete":
            row = self.j.db.execute(
                "SELECT * FROM previews WHERE id=? AND expires>?",
                (req.get("preview_id"), time.time()),
            ).fetchone()
            require(
                row and (row["owner"] == owner or row["owner"].startswith(owner + "/")),
                404,
                "Deletion preview expired or missing.",
            )
            require(
                hmac.compare_digest(
                    digest(row["manifest"]), str(req.get("manifest_digest", ""))
                ),
                409,
                "Manifest changed.",
            )
            self.j.db.execute("UPDATE previews SET approved=1 WHERE id=?", (row["id"],))
            return {"approved": True}
        raise Problem(400, "Unknown native operation.")

    def delegated(self, b):
        now = int(time.time())
        gateway = self.j.db.execute(
            "SELECT * FROM gateways WHERE id=?", (b.get("gateway_id"),)
        ).fetchone()
        require(gateway, 401, "Invalid gateway.")
        nonce = b.get("nonce", "")
        expires = b.get("expires", 0)
        require(
            isinstance(nonce, str)
            and 20 <= len(nonce) <= 128
            and isinstance(expires, int)
            and now < expires <= now + 90
            and b.get("account") == gateway["account"],
            401,
            "Invalid assertion.",
        )
        fields = [
            gateway["id"],
            gateway["account"],
            "Tlachihuani.Torrenter",
            nonce,
            expires,
        ]
        expected = hmac.new(
            gateway["secret"].encode(), packed(fields).encode(), hashlib.sha256
        ).hexdigest()
        require(
            hmac.compare_digest(expected, str(b.get("signature", ""))),
            401,
            "Invalid assertion.",
        )
        used = self.j.db.execute(
            "INSERT OR IGNORE INTO nonces VALUES(?,?)",
            (gateway["id"] + nonce, expires),
        ).rowcount
        require(used == 1, 401, "Assertion already redeemed.")
        return 201, self.j.issue(gateway["owner"], gateway["scope"], 300)

    def inspection(self, row):
        result = {
            "inspection_id": row["id"],
            "metadata_revision": 1,
            "phase": "resolving_metadata",
        }
        if row["metainfo"]:
            info, files = inspect(row["metainfo"])
            result.update(phase="ready", name=info.name(), files=files)
        elif row["pending"]:
            result["lookup_state"] = "active" if row["id"] in self.e.lookups else "queued"
        else:
            result["phase"] = "expired"
        return result

    def settings(self, owner):
        row = self.j.db.execute(
            "SELECT * FROM preferences WHERE owner=?", (owner,)
        ).fetchone()
        defaults = {
            "resume_on_boot": True,
            "seed_after_completion": False,
            "download_limit": 0,
            "upload_limit": 0,
        }
        if row:
            defaults.update(json.loads(row["settings"]))
        return {
            "root_ids": ["downloads", "archive"],
            "active_per_owner": 2,
            "active_per_host": 4,
            "stall_yield_seconds": self.e.STALL_SECONDS,
            "stalled_retry_seconds": self.e.RETRY_SECONDS,
            "revision": row["revision"] if row else 1,
            "defaults": defaults,
        }

    def edit_settings(self, owner, body, request):
        current = self.settings(owner)
        self.revision(current, request)
        require(
            body and set(body) <= set(current["defaults"]),
            422,
            "Unknown profile setting.",
        )
        for key, value in body.items():
            if key in ("download_limit", "upload_limit"):
                require(
                    type(value) is int and 0 <= value <= 2**30,
                    422,
                    "Invalid rate limit.",
                )
            else:
                require(type(value) is bool, 422, "Invalid profile policy.")
        current["defaults"].update(body)
        revision = current["revision"] + 1
        self.j.db.execute(
            "INSERT OR REPLACE INTO preferences VALUES(?,?,?)",
            (owner, revision, packed(current["defaults"])),
        )
        self.j.event(owner, None, "settings_changed")
        return {"action": "settings_changed", "revision": revision}

    def edit_labels(self, owner, kind, method, body):
        name = body.get("name")
        require(
            isinstance(name, str) and name.strip() == name and 0 < len(name) <= 80,
            422,
            "Expected a label name.",
        )
        existing = {
            r[0]
            for r in self.j.db.execute(
                "SELECT name FROM labels WHERE owner=? AND kind=?", (owner, kind)
            )
        }
        rows = self.j.db.execute(
            "SELECT id,options FROM jobs WHERE owner=? AND removed=0", (owner,)
        ).fetchall()
        options = [(row["id"], json.loads(row["options"])) for row in rows]
        for _, opts in options:
            existing.update(opts["tags"] if kind == "tags" else [opts["category"]])
        new = body.get("new_name")
        if method in ("POST", "PATCH"):
            if method == "POST":
                new = name
            require(
                isinstance(new, str) and new.strip() == new and 0 < len(new) <= 80,
                422,
                "Invalid new label.",
            )
            require(new not in existing, 409, "Label already exists.")
            self.j.db.execute("INSERT INTO labels VALUES(?,?,?)", (owner, kind, new))
        if method in ("PATCH", "DELETE"):
            require(name in existing, 404, "Label was not found.")
            self.j.db.execute(
                "DELETE FROM labels WHERE owner=? AND kind=? AND name=?",
                (owner, kind, name),
            )
            for ident, opts in options:
                if kind == "categories" and opts["category"] == name:
                    opts["category"] = new if method == "PATCH" else ""
                elif kind == "tags" and name in opts["tags"]:
                    opts["tags"] = [x for x in opts["tags"] if x != name]
                    if method == "PATCH" and new not in opts["tags"]:
                        opts["tags"].append(new)
                else:
                    continue
                self.j.db.execute(
                    "UPDATE jobs SET options=?,revision=revision+1 WHERE id=?",
                    (packed(opts), ident),
                )
                self.j.event(owner, ident, "labels_changed")
        self.j.event(owner, None, kind + "_changed")
        return {"action": kind + "_changed"}

    def dispatch(self, req):
        if req.get("admin"):
            return 200, self.native(req)
        method, path = req["method"], req.get("path") or ""
        b = req.get("body") or {}
        parts = path.split("/")
        if method == "GET" and not path:
            return 200, {
                "name": "Tlachihuani Torrenter",
                "api_version": 1,
                "workspace": "/",
                "capabilities": "/api/v1/capabilities",
                "authentication": "Bearer",
            }
        if method == "GET" and path == "health":
            return 200, {"api_version": 1, "engine": "ready"}
        if method == "POST" and path == "sessions/delegated":
            return self.delegated(b)
        cred = self.j.credential(req.get("authorization", ""))
        owner = cred["owner"]
        scopes = cred["scope"].split()

        def scope(name):
            require(name in scopes, 403, "Credential lacks " + name + " scope.")

        if method == "DELETE" and path == "sessions/current":
            self.j.db.execute("DELETE FROM tokens WHERE hash=?", (cred["hash"],))
            return 200, {"revoked": True}
        if method == "GET":
            scope("read")
            if path == "capabilities":
                return 200, {
                    "protocol_major": 1,
                    "profile_key": digest(owner),
                    "scopes": scopes,
                    "actions": [
                        "pause",
                        "resume",
                        "stop",
                        "start",
                        "cancel",
                        "recheck",
                        "move",
                        "reseed",
                    ],
                    "root_ids": ["downloads", "archive"],
                }
            if path == "torrents":
                query = req.get("query", {})
                try:
                    limit = int(query.get("limit", "100"))
                    offset = int(query.get("cursor", "0"))
                except ValueError:
                    raise Problem(400, "Invalid cursor or limit.") from None
                require(
                    1 <= limit <= 250 and offset >= 0, 400, "Invalid cursor or limit."
                )
                rows = self.j.db.execute(
                    "SELECT id,owner,snapshot,options,desired,revision,completed,root_id,created FROM jobs WHERE owner=? AND removed=0 ORDER BY created,id",
                    (owner,),
                )
                items = [self.e.snapshot(row) for row in rows]
                for name, key in (
                    ("phase", "phase"),
                    ("desired", "desired_state"),
                    ("category", "category"),
                ):
                    if query.get(name):
                        items = [item for item in items if item[key] == query[name]]
                for name, key in (("tag", "tags"), ("tracker", "tracker_hosts")):
                    if query.get(name):
                        items = [
                            item for item in items if query[name] in item.get(key, [])
                        ]
                if query.get("search"):
                    items = [
                        item
                        for item in items
                        if query["search"].casefold() in item["name"].casefold()
                    ]
                order = query.get("sort", "")
                require(
                    order
                    in (
                        "",
                        "name",
                        "phase",
                        "selected_bytes",
                        "verified_bytes",
                        "download_rate_bps",
                        "upload_rate_bps",
                        "queue_position",
                    ),
                    400,
                    "Unsupported sort.",
                )
                if order:
                    items.sort(
                        key=lambda item: (item[order], item["job_id"]),
                        reverse=query.get("direction") == "desc",
                    )
                return 200, {
                    "items": items[offset : offset + limit],
                    "total": len(items),
                    "resolving_metadata": self.j.db.execute(
                        "SELECT count(*) FROM inspections WHERE owner=? AND pending=1", (owner,)
                    ).fetchone()[0],
                    "next_cursor": offset + limit
                    if len(items) > offset + limit
                    else None,
                    "event_cursor": self.j.db.execute(
                        "SELECT coalesce(max(cursor),0) FROM events WHERE owner=?",
                        (owner,),
                    ).fetchone()[0],
                }
            if path == "events":
                try:
                    after = int(req.get("query", {}).get("after", "0"))
                except ValueError:
                    raise Problem(400, "Invalid event cursor.") from None
                floor = self.j.db.execute(
                    "SELECT value FROM event_floors WHERE owner=?", (owner,)
                ).fetchone()
                require(
                    not floor or after >= floor[0],
                    410,
                    "Event cursor expired. Read a fresh queue snapshot.",
                )
                rows = self.j.db.execute(
                    "SELECT * FROM events WHERE owner=? AND cursor>? ORDER BY cursor LIMIT 100",
                    (owner, after),
                ).fetchall()
                return 200, {
                    "events": [
                        {
                            "cursor": r["cursor"],
                            "job_id": r["job"],
                            "kind": r["kind"],
                            "at": r["at"],
                        }
                        for r in rows
                    ],
                    "next_cursor": rows[-1]["cursor"] if rows else after,
                }
            if len(parts) == 2 and parts[0] == "operations":
                row = self.j.db.execute(
                    "SELECT coalesce(outcome,result) FROM operations WHERE id=? AND owner=?",
                    (parts[1], owner),
                ).fetchone()
                require(row, 404, "Operation not found.")
                return 200, json.loads(row[0])
            if len(parts) == 2 and parts[0] == "inspections":
                row = self.get_inspection(owner, parts[1])
                return 200, self.inspection(row)
            if len(parts) == 3 and parts[0] == "inspections" and parts[2] == "activity":
                row = self.get_inspection(owner, parts[1])
                detail = {**self.inspection(row), **self.source(row["metainfo"], row["magnet"])}
                lookup = self.e.lookups.get(row["id"])
                if lookup:
                    status = lookup[1].status()
                    detail["discovery"] = {
                        "known_peers": status.list_peers, "connected_peers": status.num_peers,
                        "listening": self.e.sessions[owner].is_listening(),
                        "paused": status.paused, "error_code": status.errc.value(),
                    }
                return 200, detail
            if parts[0] == "torrents" and len(parts) in (2, 3):
                row = self.j.job(owner, parts[1])
                if len(parts) == 2:
                    return 200, self.e.snapshot(row)
                return 200, self.detail(row, parts[2])
            if path in ("categories", "tags", "statistics", "settings"):
                values = [
                    self.e.snapshot(r)
                    for r in self.j.db.execute(
                        "SELECT * FROM jobs WHERE owner=? AND removed=0", (owner,)
                    )
                ]
                if path == "statistics":
                    return 200, {
                        "downloads": len(values),
                        "download_rate_bps": sum(
                            v.get("download_rate_bps", 0) for v in values
                        ),
                    }
                if path == "settings":
                    return 200, self.settings(owner)
                labels = {
                    r[0]
                    for r in self.j.db.execute(
                        "SELECT name FROM labels WHERE owner=? AND kind=?",
                        (owner, path),
                    )
                }
                return 200, {
                    "items": sorted(
                        labels
                        | {
                            v
                            for job in values
                            for v in (
                                job.get("tags", [])
                                if path == "tags"
                                else [job.get("category", "")]
                            )
                            if v
                        }
                    )
                }
        if method == "PATCH" and path == "settings":
            scope("control")
            return self.j.mutate(
                req, cred, lambda op: self.edit_settings(owner, b, req)
            )
        if method in ("POST", "PATCH", "DELETE") and path in ("categories", "tags"):
            scope("control")
            return self.j.mutate(
                req, cred, lambda op: self.edit_labels(owner, path, method, b)
            )
        if method == "POST" and path == "inspections":
            scope("submit")
            active = self.j.db.execute(
                "SELECT count(*) FROM inspections WHERE owner=? AND (pending=1 OR expires>?)",
                (owner, time.time()),
            ).fetchone()[0]
            require(active < 32, 429, "Inspection limit reached.")
            ident = new_id()
            raw = None
            if "metainfo" in b:
                raw = base64.b64decode(b["metainfo"], validate=True)
                info, files = inspect(raw)
                for tracker in info.trackers():
                    endpoint(tracker.url)
                for seed in info.web_seeds():
                    endpoint(seed["url"])
            else:
                self.e.magnet_parameters(b.get("magnet"))
            self.j.db.execute(
                "INSERT INTO inspections(id,owner,metainfo,magnet,expires,pending) VALUES(?,?,?,?,?,?)",
                (ident, owner, raw, b.get("magnet"), int(time.time()) + 900, int(raw is None)),
            )
            if raw is None:
                self.e.fill_lookup_slots()
            return 201, self.inspection(self.get_inspection(owner, ident))
        if method == "POST" and path == "torrents":
            scope("submit")
            return self.j.mutate(req, cred, lambda op: self.submit(owner, b))
        if method == "POST" and path == "batch-operations":
            scope("control")

            def batch(op):
                items = b.get("jobs")
                action = b.get("action")
                require(
                    action in ("pause", "resume", "stop", "start")
                    and isinstance(items, list)
                    and 0 < len(items) <= 100,
                    422,
                    "Invalid batch operation.",
                )
                require(
                    all(
                        isinstance(i, dict)
                        and isinstance(i.get("job_id"), str)
                        and type(i.get("revision")) is int
                        for i in items
                    ),
                    422,
                    "Each item needs job_id and revision.",
                )
                require(
                    len({i["job_id"] for i in items}) == len(items),
                    422,
                    "Duplicate job in batch.",
                )
                results = []
                for item in items:
                    ident = item["job_id"]
                    try:
                        result = self.change(
                            owner,
                            ["torrents", ident, "actions"],
                            "POST",
                            {"action": action},
                            {"revision": '"' + str(item["revision"]) + '"'},
                        )
                        results.append(dict(result, ok=True))
                    except Problem as exc:
                        results.append(
                            {
                                "job_id": ident,
                                "ok": False,
                                "status": exc.status,
                                "error": str(exc),
                            }
                        )
                return {"action": action, "items": results}

            return self.j.mutate(req, cred, batch)
        if method == "POST" and path == "content-deletion-previews":
            scope("erase")
            row = self.j.job(owner, b.get("job_id"))
            self.revision(row, req)
            require(
                row["id"] not in self.e.handles
                and row["id"] not in self.e.delivery.pending
                and (row["desired"] in ("stopped", "cancelled") or row["completed"]),
                409,
                "Stop this job before deleting files.",
            )
            manifest = packed(self.manifest(row))
            require(
                len(manifest) < 60000,
                413,
                "Manifest exceeds the native approval limit.",
            )
            ident = new_id()
            self.j.db.execute(
                "INSERT INTO previews VALUES(?,?,?,?,?,?,0)",
                (
                    ident,
                    owner,
                    row["id"],
                    row["revision"],
                    manifest,
                    int(time.time()) + 120,
                ),
            )
            return 201, {
                "preview_id": ident,
                "manifest_digest": digest(manifest),
                "files": json.loads(manifest),
                "revision": row["revision"],
            }
        if method == "POST" and path == "content-deletions":
            scope("erase")

            def erase(op):
                preview = self.j.db.execute(
                    "SELECT * FROM previews WHERE id=? AND owner=? AND expires>?",
                    (b.get("preview_id"), owner, time.time()),
                ).fetchone()
                require(
                    preview and preview["approved"],
                    403,
                    "Approve this file manifest in XT first.",
                )
                row = self.j.job(owner, preview["job"])
                self.revision(row, req)
                require(
                    row["revision"] == preview["revision"]
                    and packed(self.manifest(row)) == preview["manifest"]
                    and row["id"] not in self.e.handles,
                    409,
                    "Files or job changed.",
                )
                self.j.db.execute(
                    "INSERT INTO deletions VALUES(?,?,?,?)",
                    (op, row["id"], owner, preview["manifest"]),
                )
                self.j.db.execute("DELETE FROM previews WHERE id=?", (preview["id"],))
                self.j.db.execute(
                    "UPDATE jobs SET revision=revision+1,desired='stopped',completed=NULL,resume=NULL WHERE id=?",
                    (row["id"],),
                )
                return {"job_id": row["id"], "revision": row["revision"] + 1}

            return self.j.mutate(req, cred, erase)
        if parts[0] == "torrents" and len(parts) in (2, 3):
            scope("remove" if method == "DELETE" else "control")
            return self.j.mutate(
                req, cred, lambda op: self.change(owner, parts, method, b, req, op)
            )
        raise Problem(404, "Unknown API route.")

    def get_inspection(self, owner, ident):
        row = self.j.db.execute(
            "SELECT * FROM inspections WHERE owner=? AND id=? AND (pending=1 OR expires>?)",
            (owner, ident, time.time()),
        ).fetchone()
        require(row, 404, "Inspection expired or missing.")
        return row

    @staticmethod
    def priorities(body, selected):
        values = body.get("priorities", {})
        require(
            isinstance(values, dict)
            and set(values) <= set(map(str, selected))
            and all(type(v) is int and 1 <= v <= 7 for v in values.values()),
            422,
            "File priority must be 1 through 7 for a selected file.",
        )
        return values

    def submit(self, owner, b):
        inspection = self.get_inspection(owner, b.get("inspection_id"))
        require(
            inspection["metainfo"] and b.get("metadata_revision") == 1,
            409,
            "Wait for reviewed metadata.",
        )
        require(
            b.get("destination_root_id") in ("downloads", "archive"),
            422,
            "Unknown storage root.",
        )
        require(
            type(b.get("seed_after_completion", False)) is bool,
            422,
            "seed_after_completion must be a boolean.",
        )
        info, files = inspect(inspection["metainfo"])
        selected = b.get("selected_file_ids")
        valid = {f["id"] for f in files}
        require(
            isinstance(selected, list)
            and selected
            and all(type(i) is int and i in valid for i in selected),
            422,
            "Invalid file selection.",
        )
        selected = sorted(set(selected))
        rows = self.j.db.execute(
            "SELECT snapshot,desired FROM jobs WHERE owner=? AND removed=0", (owner,)
        ).fetchall()
        require(len(rows) < 100, 429, "Owner queue is full.")
        infohash = str(info.info_hashes().v1) + ":" + str(info.info_hashes().v2)
        require(
            not any(
                json.loads(r[0]).get("info_hash") == infohash
                for r in rows
                if r["desired"] != "cancelled"
            ),
            409,
            "This torrent is already in the queue.",
        )
        ident = new_id()
        defaults = self.settings(owner)["defaults"]
        resume = b.get("resume_on_boot", defaults["resume_on_boot"])
        require(type(resume) is bool, 422, "resume_on_boot must be a boolean.")
        opts = {
            **defaults,
            "priorities": self.priorities(b, selected),
            "resume_on_boot": resume,
            "seed_after_completion": b.get(
                "seed_after_completion", defaults["seed_after_completion"]
            ),
            "category": "",
            "tags": [],
            "queue_position": len(rows),
        }
        if inspection["magnet"]:
            opts["bootstrap_magnet"] = inspection["magnet"]
        snapshot = {
            "tracker_hosts": sorted({endpoint(t.url) for t in info.trackers()}),
            "name": info.name(),
            "total_bytes": info.total_size(),
            "info_hash": infohash,
            "selected_bytes": sum(f["size"] for f in files if f["id"] in selected),
            "verified_bytes": 0,
        }
        pending = self.j.db.execute(
            "SELECT coalesce(sum(max(0,json_extract(snapshot,'$.selected_bytes')-coalesce(json_extract(snapshot,'$.verified_bytes'),0))),0) FROM jobs WHERE removed=0 AND desired!='cancelled' AND completed IS NULL"
        ).fetchone()[0]
        require(
            snapshot["selected_bytes"] + pending + 64 * 1024 * 1024
            < shutil.disk_usage(self.j.root).free,
            507,
            "Insufficient reserved storage for this selection.",
        )
        self.j.db.execute(
            "INSERT INTO jobs(id,owner,metainfo,selection,options,desired,snapshot,created) VALUES(?,?,?,?,?,'running',?,?)",
            (
                ident,
                owner,
                inspection["metainfo"],
                packed(selected),
                packed(opts),
                packed(snapshot),
                int(time.time()),
            ),
        )
        self.j.db.execute(
            "UPDATE jobs SET root_id=? WHERE id=?", (b["destination_root_id"], ident)
        )
        self.j.event(owner, ident, "accepted")
        return {
            "job_id": ident,
            "revision": 1,
            "desired_state": "running",
            "observed_state": "queued",
        }

    @staticmethod
    def revision(row, req):
        require(
            req.get("revision") == f'"{row["revision"]}"',
            412,
            "Job changed. Read its current revision before retrying.",
        )

    def change(self, owner, parts, method, b, req, op=None):
        row = self.j.job(owner, parts[1])
        self.revision(row, req)
        ident = row["id"]
        state = row["desired"]
        action = b.get("action")
        require(
            not self.j.db.execute(
                "SELECT 1 FROM deletions WHERE job=?", (ident,)
            ).fetchone(),
            409,
            "File deletion in progress.",
        )
        require(
            not self.j.db.execute(
                "SELECT 1 FROM moves WHERE job=?", (ident,)
            ).fetchone(),
            409,
            "Relocation in progress.",
        )
        if method == "DELETE" and len(parts) == 2:
            require(
                ident not in self.e.handles
                and (state in ("cancelled", "stopped") or row["completed"]),
                409,
                "Stop the download before removing it.",
            )
            self.j.db.execute("UPDATE jobs SET removed=1 WHERE id=?", (ident,))
            action = "removed"
        elif method == "POST" and parts[2:] == ["actions"]:
            transitions = {
                "pause": ("running", "paused"),
                "resume": ("paused", "running"),
                "stop": (("running", "paused"), "stopped"),
                "start": ("stopped", "running"),
            }
            if action == "move":
                dest = b.get("destination_root_id")
                require(
                    dest in ("downloads", "archive") and dest != row["root_id"],
                    422,
                    "Select a different approved root.",
                )
                require(
                    state == "stopped" and ident not in self.e.handles,
                    409,
                    "Stop the download before moving it.",
                )
                require(
                    not self.j.files_root(row, dest).exists(),
                    409,
                    "Destination already exists.",
                )
                self.j.db.execute(
                    "INSERT INTO moves VALUES(?,?,?,?)", (op, ident, owner, dest)
                )
            elif action == "reseed":
                require(
                    row["completed"] and state != "cancelled",
                    409,
                    "Verified content is required for reseeding.",
                )
                options = json.loads(row["options"])
                options["seed_after_completion"] = True
                options["seed_until"] = int(time.time()) + 3600
                options["seed_finished"] = False
                self.j.db.execute(
                    "UPDATE jobs SET options=? WHERE id=?", (packed(options), ident)
                )
                state = "running"
            elif action == "cancel":
                require(not row["completed"], 409, "This job has already completed.")
                state = "cancelled"
            elif action == "recheck":
                require(
                    state not in ("cancelled",),
                    409,
                    "Cancelled job cannot be rechecked.",
                )
                self.j.db.execute(
                    "UPDATE jobs SET completed=NULL,resume=NULL WHERE id=?", (ident,)
                )
                if ident in self.e.handles:
                    self.e.handles[ident].force_recheck()
                    if ident not in self.e.pending_release:
                        self.e.handles[ident].resume()
                self.e.verification_wait.pop(ident, None)
                self.e.disk_quiet.discard(ident)
                state = "running"
            else:
                require(action in transitions, 422, "Unknown transfer action.")
                before, after = transitions[action]
                require(
                    state == after
                    or state in (before if isinstance(before, tuple) else (before,)),
                    409,
                    "Action conflicts with current state.",
                )
                state = after
            self.e.failures.pop(ident, None)
            if state == "running":
                self.e.retry_after.pop(ident, None)
                self.e.queue_turn.pop(ident, None)
                self.e.progress.pop(ident, None)
        elif method == "PATCH" and len(parts) == 2:
            options = json.loads(row["options"])
            require(
                b
                and set(b)
                <= {
                    "queue_position",
                    "download_limit",
                    "upload_limit",
                    "category",
                    "tags",
                    "resume_on_boot",
                    "seed_after_completion",
                },
                422,
                "Unknown option.",
            )
            for k, v in b.items():
                if k in ("download_limit", "upload_limit"):
                    require(
                        type(v) is int and 0 <= v <= 2**30, 422, "Invalid rate limit."
                    )
                if k == "queue_position":
                    require(
                        type(v) is int and 0 <= v < 10000,
                        422,
                        "Invalid queue position.",
                    )
                if k == "category":
                    require(
                        isinstance(v, str) and len(v) <= 80, 422, "Invalid category."
                    )
                if k == "tags":
                    require(
                        isinstance(v, list)
                        and len(v) <= 16
                        and all(isinstance(t, str) and len(t) <= 80 for t in v),
                        422,
                        "Invalid tags.",
                    )
                if k in ("resume_on_boot", "seed_after_completion"):
                    require(type(v) is bool, 422, "Expected boolean.")
            options.update(b)
            self.j.db.execute(
                "UPDATE jobs SET options=? WHERE id=?", (packed(options), ident)
            )
            if ident in self.e.handles:
                self.e.handles[ident].set_download_limit(options["download_limit"])
                self.e.handles[ident].set_upload_limit(options["upload_limit"])
            action = "updated"
        elif method == "PATCH" and parts[2:] in (["trackers"], ["web-seeds"]):
            require(
                state == "stopped" and ident not in self.e.handles,
                409,
                "Stop the job before editing its network sources.",
            )
            urls = b.get("urls")
            require(
                isinstance(urls, list)
                and len(urls) <= 32
                and all(isinstance(u, str) and len(u) <= 2048 for u in urls),
                422,
                "Invalid source list.",
            )
            for url in urls:
                endpoint(url)
                if parts[2] == "web-seeds":
                    require(
                        urlsplit(url).scheme in ("http", "https"),
                        422,
                        "A web seed needs HTTP or HTTPS.",
                    )
            options = json.loads(row["options"])
            options["trackers" if parts[2] == "trackers" else "web_seeds"] = list(
                dict.fromkeys(urls)
            )
            self.j.db.execute(
                "UPDATE jobs SET options=?,resume=NULL WHERE id=?",
                (packed(options), ident),
            )
            if parts[2] == "trackers":
                snap = json.loads(row["snapshot"])
                snap["tracker_hosts"] = sorted({endpoint(url) for url in urls})
                self.j.db.execute(
                    "UPDATE jobs SET snapshot=? WHERE id=?", (packed(snap), ident)
                )
            action = "sources_changed"
        elif method == "PATCH" and parts[2:] == ["files"]:
            require(
                state == "stopped" and ident not in self.e.handles,
                409,
                "Stop the job before changing its selection.",
            )
            _, files = inspect(row["metainfo"])
            selected = b.get("selected_file_ids")
            require(
                isinstance(selected, list)
                and selected
                and all(
                    type(i) is int and i in {f["id"] for f in files} for i in selected
                ),
                422,
                "Invalid file selection.",
            )
            opts = json.loads(row["options"])
            opts["priorities"] = self.priorities(b, selected)
            self.j.db.execute(
                "UPDATE jobs SET options=? WHERE id=?", (packed(opts), ident)
            )
            snap = json.loads(row["snapshot"])
            snap.update(
                selected_bytes=sum(f["size"] for f in files if f["id"] in selected),
                verified_bytes=0,
            )
            self.j.db.execute(
                "UPDATE jobs SET selection=?,snapshot=?,completed=NULL,resume=NULL WHERE id=?",
                (packed(sorted(set(selected))), packed(snap), ident),
            )
            action = "selection_changed"
        else:
            raise Problem(404, "Unknown job operation.")
        self.j.db.execute(
            "UPDATE jobs SET revision=revision+1,desired=? WHERE id=?", (state, ident)
        )
        self.j.event(owner, ident, action)
        return {
            "job_id": ident,
            "action": action,
            "revision": row["revision"] + 1,
            "desired_state": state,
        }

    def manifest(self, row):
        _, files = inspect(row["metainfo"])
        result = []
        roots = [("service", self.j.files_root(row))]
        delivered = self.e.delivery.status(row).get("saved_to")
        if delivered:
            roots.append(("downloads", plain_path(delivered)))
        for location, root in roots:
            for file in files:
                path = safe_file(root, file["path"])
                if io_path(path).is_file():
                    st = io_path(path).stat()
                    require(st.st_nlink == 1, 409, "Shared file cannot be erased.")
                    result.append(
                        {
                            "path": file["path"], "location": location, "absolute_path": str(path),
                            "bytes": st.st_size,
                            "mtime_ns": str(st.st_mtime_ns),
                            "file_id": str(st.st_ino),
                        }
                    )
        return result

    @staticmethod
    def source(metainfo, original):
        if original:
            return {"source_kind": "magnet", "magnet": original}
        info, _ = inspect(metainfo)
        return {"source_kind": "metainfo", "magnet": lt.make_magnet_uri(info)}

    def detail(self, row, part):
        info, files = inspect(row["metainfo"])
        h = self.e.handles.get(row["id"])
        if part == "activity":
            # Source URIs are available only on this explicitly requested,
            # owner-scoped route. Status snapshots and lists omit private trackers.
            source = self.source(row["metainfo"], json.loads(row["options"]).get("bootstrap_magnet"))
            return {**source, "name": info.name(), "phase": self.e.snapshot(row)["phase"],
                    "files": self.detail(row, "files")["items"], "publication": self.detail(row, "manifest")}
        if part == "files":
            selected = set(json.loads(row["selection"]))
            return {
                "items": [
                    dict(
                        f,
                        selected=f["id"] in selected,
                        priority=json.loads(row["options"])
                        .get("priorities", {})
                        .get(str(f["id"]), 4)
                        if f["id"] in selected
                        else 0,
                    )
                    for f in files
                ]
            }
        if part == "manifest":
            published = self.j.db.execute(
                "SELECT manifest FROM published WHERE job=?", (row["id"],)
            ).fetchone()
            ready = bool(row["completed"] and published)
            delivery = self.e.delivery.status(row)
            return {
                "files": json.loads(published[0]) if ready else [],
                "verified": ready and delivery["delivery_state"] in ("saved", "service_store"),
                "download_verified": ready,
                "output_root": (delivery.get("saved_to") or str(self.j.files_root(row))) if ready else None,
                "service_output_root": str(self.j.files_root(row)) if ready else None,
                **delivery,
            }
        opts = json.loads(row["options"])
        if part == "trackers" and "trackers" in opts:
            return {
                "items": [
                    {"host": urlsplit(url).hostname, "tier": i}
                    for i, url in enumerate(opts["trackers"])
                ]
            }
        if part == "web-seeds" and "web_seeds" in opts:
            return {
                "items": [{"host": urlsplit(url).hostname} for url in opts["web_seeds"]]
            }
        if part == "trackers":
            return {
                "items": [
                    {"host": urlsplit(t.url).hostname, "tier": t.tier}
                    for t in info.trackers()
                ]
            }
        if part == "web-seeds":
            return {
                "items": [
                    {"host": urlsplit(t["url"]).hostname} for t in info.web_seeds()
                ]
            }
        if part == "peers":
            return {
                "items": [
                    {"endpoint": str(x.ip), "down": x.down_speed, "up": x.up_speed}
                    for x in h.get_peer_info()[:100]
                ]
                if h
                else []
            }
        if part == "statistics":
            return self.e.snapshot(row)
        raise Problem(404, "Unknown detail resource.")

    def settle_receipts(self):
        pending = self.j.db.execute(
            "SELECT id,owner,result FROM operations WHERE outcome IS NULL LIMIT 500"
        ).fetchall()
        for row in pending:
            result = json.loads(row["result"])
            if self.j.db.execute(
                "SELECT 1 FROM deletions WHERE op=? UNION SELECT 1 FROM moves WHERE op=?",
                (row["id"], row["id"]),
            ).fetchone():
                continue
            target = self.j.db.execute(
                "SELECT * FROM jobs WHERE owner=? AND id=?",
                (row["owner"], result.get("job_id")),
            ).fetchone()
            action = result.get("action")
            if target and action in ("pause", "stop", "cancel"):
                current = self.e.snapshot(target)
                if current["phase"] in ("pausing", "stopping", "cancelling"):
                    continue
                result["observed_state"] = current["phase"]
                result["phase"] = (
                    "succeeded"
                    if current["desired_state"] == result["desired_state"]
                    else "superseded"
                )
            else:
                result["phase"] = "succeeded"
            self.j.db.execute(
                "UPDATE operations SET outcome=? WHERE id=?",
                (packed(result), row["id"]),
            )

    def reconcile_moves(self):
        for intent in self.j.db.execute("SELECT * FROM moves").fetchall():
            row = self.j.job(intent["owner"], intent["job"])
            outcome = json.loads(
                self.j.db.execute(
                    "SELECT result FROM operations WHERE id=?", (intent["op"],)
                ).fetchone()[0]
            )
            try:
                source = self.j.files_root(row)
                target = self.j.files_root(row, intent["destination"])
                target.parent.mkdir(parents=True, exist_ok=True)
                if source.exists():
                    require(not target.exists(), 409, "Destination is occupied.")
                    source.rename(target)
                # An interrupted same-volume rename has a target and no source.
                # A queued job with no files may have neither.
                self.j.db.execute(
                    "UPDATE jobs SET root_id=?,resume=NULL WHERE id=?",
                    (intent["destination"], row["id"]),
                )
                outcome["phase"] = "succeeded"
            except (Problem, OSError) as exc:
                outcome.update(phase="failed", error=str(exc))
            self.j.db.execute(
                "UPDATE operations SET outcome=? WHERE id=?",
                (packed(outcome), intent["op"]),
            )
            self.j.db.execute("DELETE FROM moves WHERE op=?", (intent["op"],))
            self.j.event(row["owner"], row["id"], "move_" + outcome["phase"])

    def reconcile_deletions(self):
        for pending in self.j.db.execute("SELECT * FROM deletions").fetchall():
            row = self.j.job(pending["owner"], pending["job"])
            result = json.loads(
                self.j.db.execute(
                    "SELECT result FROM operations WHERE id=?", (pending["op"],)
                ).fetchone()[0]
            )
            try:
                for entry in json.loads(pending["manifest"]):
                    root = self.j.files_root(row)
                    if entry.get("location") == "downloads":
                        delivered = self.e.delivery.status(row).get("saved_to")
                        require(delivered, 409, "The delivery destination changed after approval.")
                        root = plain_path(delivered)
                    path = safe_file(root, entry["path"])
                    require(entry.get("absolute_path", str(path)) == str(path), 409, "The reviewed path changed.")
                    if not io_path(path).exists():
                        continue
                    st = io_path(path).stat()
                    require(
                        st.st_nlink == 1
                        and [st.st_size, str(st.st_mtime_ns), str(st.st_ino)]
                        == [entry["bytes"], entry["mtime_ns"], entry["file_id"]],
                        409,
                        "File changed since preview.",
                    )
                    io_path(path).unlink()
                result["phase"] = "succeeded"
                self.j.db.execute("DELETE FROM published WHERE job=?", (row["id"],))
                self.j.db.execute("DELETE FROM deliveries WHERE job=?", (row["id"],))
                self.j.db.execute("DELETE FROM delivery_locations WHERE job=?", (row["id"],))
                snap = json.loads(row["snapshot"])
                snap["verified_bytes"] = 0
                self.j.db.execute(
                    "UPDATE jobs SET snapshot=? WHERE id=?", (packed(snap), row["id"])
                )
            except (OSError, Problem) as exc:
                result.update(phase="failed", error=str(exc))
            self.j.db.execute(
                "UPDATE operations SET outcome=? WHERE id=?",
                (packed(result), pending["op"]),
            )
            self.j.db.execute("DELETE FROM deletions WHERE op=?", (pending["op"],))
            self.j.event(row["owner"], row["id"], "content_deletion_" + result["phase"])
