"""Single-writer job journal. Only the provider process opens this database."""

import hashlib
import json
import os
import re
import secrets
import sqlite3
import stat
import time
import uuid
from pathlib import Path


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def require(condition, status, message):
    if not condition:
        raise Problem(status, message)


def new_id():
    return uuid.uuid4().hex


def packed(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


_LONG_PREFIX = "\\\\?\\"


def io_path(path):
    """Return the form of ``path`` that Windows file APIs accept at any length.

    Torrent paths are nested below a long service root, so a file easily passes
    MAX_PATH (260 characters). Without the extended-length prefix, stat, open and
    rename fail for it unless long paths are enabled machine-wide. Use this only
    for file I/O: stored, displayed and compared paths keep their plain form.
    """
    text = os.fspath(path)
    if os.name != "nt" or text.startswith(_LONG_PREFIX):
        return Path(text)
    text = os.path.abspath(text)
    if text.startswith("\\\\"):
        return Path(_LONG_PREFIX + "UNC\\" + text[2:])
    return Path(_LONG_PREFIX + text)


def safe_file(root, relative):
    parts = relative.replace("\\", "/").split("/")
    path = Path(root)
    for item in [path] + [path.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]:
        probe = io_path(item)
        if (
            probe.is_symlink()
            or os.path.lexists(probe)
            and getattr(probe.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise Problem(409, "A storage path is a reparse point.")
    result = path.joinpath(*parts)
    require(
        io_path(result).resolve().is_relative_to(io_path(path).resolve())
        and all(p not in ("", ".", "..") for p in parts),
        422,
        "Invalid relative path.",
    )
    return result


class Journal:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.root / "jobs.sqlite")
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS inspections(id TEXT PRIMARY KEY,owner TEXT NOT NULL,metainfo BLOB,magnet TEXT,expires INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT NOT NULL,metainfo BLOB NOT NULL,selection TEXT NOT NULL,
            options TEXT NOT NULL,desired TEXT NOT NULL,revision INTEGER NOT NULL DEFAULT 1,removed INTEGER NOT NULL DEFAULT 0,
            snapshot TEXT NOT NULL DEFAULT '{}',resume BLOB,created INTEGER NOT NULL,completed INTEGER);
          CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,owner TEXT NOT NULL,request_key TEXT NOT NULL,hash TEXT NOT NULL,
            result TEXT NOT NULL,UNIQUE(owner,request_key));
          CREATE TABLE IF NOT EXISTS events(cursor INTEGER PRIMARY KEY AUTOINCREMENT,owner TEXT NOT NULL,job TEXT,kind TEXT NOT NULL,at INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS tokens(hash TEXT PRIMARY KEY,owner TEXT NOT NULL,expires INTEGER NOT NULL,scope TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS previews(id TEXT PRIMARY KEY,owner TEXT NOT NULL,job TEXT NOT NULL,revision INTEGER NOT NULL,
            manifest TEXT NOT NULL,expires INTEGER NOT NULL,approved INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS deletions(op TEXT PRIMARY KEY,job TEXT NOT NULL,owner TEXT NOT NULL,manifest TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS gateways(id TEXT PRIMARY KEY,owner TEXT NOT NULL,account TEXT NOT NULL,secret TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS nonces(id TEXT PRIMARY KEY,expires INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS owner_jobs ON jobs(owner,removed,created);
          CREATE TABLE IF NOT EXISTS event_floors(owner TEXT PRIMARY KEY,value INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS owner_events ON events(owner,cursor);
        """)
        # Upgrade earlier databases without invalidating existing receipts or granting extra scopes.
        if "pending" not in {r[1] for r in self.db.execute("PRAGMA table_info(inspections)")}:
            self.db.execute("ALTER TABLE inspections ADD COLUMN pending INTEGER NOT NULL DEFAULT 0")
            # Older workers kept active handles in memory only. Give still-valid
            # unfinished magnets a chance to resolve when upgrading that database.
            self.db.execute(
                "UPDATE inspections SET pending=1 WHERE magnet IS NOT NULL "
                "AND metainfo IS NULL AND expires>?", (time.time(),)
            )
        self.db.execute("CREATE INDEX IF NOT EXISTS inspection_pending ON inspections(pending) WHERE pending=1")
        if "scope" not in {
            r[1] for r in self.db.execute("PRAGMA table_info(gateways)")
        }:
            self.db.execute(
                "ALTER TABLE gateways ADD COLUMN scope TEXT NOT NULL DEFAULT 'read'"
            )
        if "outcome" not in {
            r[1] for r in self.db.execute("PRAGMA table_info(operations)")
        }:
            self.db.execute("ALTER TABLE operations ADD COLUMN outcome TEXT")
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS pending_operations ON operations(id) WHERE outcome IS NULL"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS published(job TEXT PRIMARY KEY, manifest TEXT NOT NULL)"
        )
        if "root_id" not in {r[1] for r in self.db.execute("PRAGMA table_info(jobs)")}:
            self.db.execute(
                "ALTER TABLE jobs ADD COLUMN root_id TEXT NOT NULL DEFAULT 'downloads'"
            )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS moves(op TEXT PRIMARY KEY, job TEXT UNIQUE, owner TEXT, destination TEXT)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS preferences(owner TEXT PRIMARY KEY, revision INTEGER NOT NULL, settings TEXT NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS labels(owner TEXT, kind TEXT, name TEXT, PRIMARY KEY(owner,kind,name))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS delivery_roots(owner TEXT PRIMARY KEY,path TEXT,error TEXT)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS fallback_roots(owner TEXT PRIMARY KEY,path TEXT,error TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS delivery_locations(job TEXT PRIMARY KEY,kind TEXT,primary_error TEXT)")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS deliveries(job TEXT PRIMARY KEY,revision INTEGER,path TEXT,files TEXT,error TEXT)"
        )
        self.db.commit()

    def event(self, owner, job, kind):
        self.db.execute(
            "INSERT INTO events(owner,job,kind,at) VALUES(?,?,?,?)",
            (owner, job, kind, int(time.time())),
        )

    def job(self, owner, job_id):
        row = self.db.execute(
            "SELECT * FROM jobs WHERE owner=? AND id=? AND removed=0", (owner, job_id)
        ).fetchone()
        require(row, 404, "Download not found.")
        return row

    def files_root(self, row, destination=None):
        key = destination if destination is not None else row["root_id"]
        require(key in ("downloads", "archive"), 422, "Unknown storage root.")
        parts = ["downloads", digest(row["owner"])]
        if key == "archive":
            parts.append("archive")
        return safe_file(self.root, "/".join([*parts, row["id"]]))

    def issue(self, owner, scope, lifetime):
        token = secrets.token_urlsafe(36)
        self.db.execute(
            "INSERT INTO tokens VALUES(?,?,?,?)",
            (digest(token), owner, int(time.time()) + lifetime, scope),
        )
        return {"access_token": token, "expires_in": lifetime, "scope": scope}

    def credential(self, authorization):
        require(
            authorization.startswith("Bearer ") and len(authorization) < 256,
            401,
            "A Torrenter credential is required.",
        )
        row = self.db.execute(
            "SELECT * FROM tokens WHERE hash=? AND expires>?",
            (digest(authorization[7:]), int(time.time())),
        ).fetchone()
        require(row, 401, "Session expired or revoked.")
        return row

    def mutate(self, req, cred, handler):
        key = req.get("key", "")
        require(
            isinstance(key, str) and re.fullmatch(r"[\w.:-]{1,128}", key),
            400,
            "A valid Idempotency-Key is required.",
        )
        signature = digest(
            packed(
                [req["method"], req["path"], req.get("revision", ""), req.get("body")]
            )
        )
        cached = self.db.execute(
            "SELECT * FROM operations WHERE owner=? AND request_key=?",
            (cred["owner"], key),
        ).fetchone()
        if cached:
            require(
                cached["hash"] == signature,
                409,
                "Idempotency key already used with different arguments.",
            )
            return 202, json.loads(cached["result"])
        op = new_id()
        result = {
            "operation_id": op,
            "phase": "accepted",
            "receipt_durable": True,
            **handler(op),
        }
        self.db.execute(
            "INSERT INTO operations(id,owner,request_key,hash,result) VALUES(?,?,?,?,?)",
            (op, cred["owner"], key, signature, packed(result)),
        )
        return 202, result
