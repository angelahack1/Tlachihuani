"""Installed-layout check using a private local tracker and a real libtorrent seed."""

import contextlib
import hashlib
import hmac
import http.server as server
import json
import os
from pathlib import Path
import secrets
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid

import libtorrent as lt


def eventually(action, timeout=30):
    end = time.monotonic() + timeout
    last = None
    while time.monotonic() < end:
        try:
            last = action()
            if last:
                return last
        except (OSError, AssertionError) as exc:
            last = str(exc)
        time.sleep(0.2)
    raise AssertionError(f"Deadline expired: {last}")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main(executable, work):
    host_id = uuid.uuid4().hex
    port = free_port()
    service = None

    def launch():
        nonlocal service
        service = subprocess.Popen(
            [executable, "--console", str(work / "state"), host_id, str(port)]
        )

    def native(**body):
        ctl = subprocess.run(
            [executable, "--dev-control", host_id, str(service.pid)],
            input=json.dumps(body) + "\n",
            capture_output=True,
            text=True,
            timeout=23,
        )
        assert ctl.returncode == 0, ctl.stderr
        return json.loads(ctl.stdout)

    def http(
        method,
        route,
        body=None,
        token=None,
        key=None,
        revision=None,
        status=200,
        headers=None,
    ):
        hdr = {"Content-Type": "application/json", **(headers or {})}
        if token:
            hdr["Authorization"] = "Bearer " + token
        if key:
            hdr["Idempotency-Key"] = key
        if revision:
            hdr["If-Match"] = f'"{revision}"'
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/" + route,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers=hdr,
        )
        try:
            response = urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            assert response.status == status, (
                method,
                route,
                response.status,
                raw[:300],
            )
            return json.loads(raw) if raw else {}

    seed = lt.session(
        {
            "listen_interfaces": "127.0.0.1:0",
            "enable_dht": False,
            "enable_lsd": False,
            "enable_upnp": False,
            "enable_natpmp": False,
            "allow_multiple_connections_per_ip": True,
        }
    )
    seed_port = eventually(seed.listen_port)

    class Tracker(server.BaseHTTPRequestHandler):
        def do_GET(self):
            data = lt.bencode(
                {
                    b"interval": 1,
                    b"peers": socket.inet_aton("127.0.0.1")
                    + struct.pack("!H", seed_port),
                }
            )
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    tracker = server.ThreadingHTTPServer(("127.0.0.1", 0), Tracker)
    threading.Thread(target=tracker.serve_forever, daemon=True).start()
    try:
        launch()
        eventually(lambda: http("GET", "health").get("engine") == "ready")
        print("PASS independent host and loopback HTTP ready", flush=True)
        http("GET", "torrents", status=401)
        http(
            "GET", "health", headers={"Origin": "http://untrusted.invalid"}, status=403
        )
        verifier = secrets.token_urlsafe(32)
        challenge = http(
            "POST",
            "session-challenges",
            {"verifier_hash": hashlib.sha256(verifier.encode()).hexdigest()},
            status=201,
        )
        exchange = {"challenge_id": challenge["challenge_id"], "verifier": verifier}
        http("POST", "sessions", exchange, status=409)
        assert native(op="approve", code=challenge["code"])["body"]["approved"]
        token = http("POST", "sessions", exchange, status=201)["access_token"]
        other = native(op="issue", profile="isolated-test-owner", scope="read")["body"][
            "access_token"
        ]
        profile = "future-agent-test"
        enrollment = native(op="issue", profile=profile, scope="read", gateway=True)[
            "body"
        ]
        nonce = secrets.token_urlsafe(24)
        expires = int(time.time()) + 45
        signed = [
            enrollment["gateway_id"],
            profile,
            "Tlachihuani.Torrenter",
            nonce,
            expires,
        ]
        signature = hmac.new(
            enrollment["signing_key"].encode(),
            json.dumps(signed, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        assertion = {
            "gateway_id": enrollment["gateway_id"],
            "account": profile,
            "nonce": nonce,
            "expires": expires,
            "signature": signature,
        }
        delegated = http("POST", "sessions/delegated", assertion, status=201)[
            "access_token"
        ]
        assert http("GET", "capabilities", token=delegated)["scopes"] == ["read"]
        http("POST", "sessions/delegated", assertion, status=401)
        http("POST", "inspections", {}, delegated, status=403)
        assert native(op="catalog")["providers"][0]["provider"] == "torrenter"
        assert native(op="stop", provider="not-a-provider")["code"] == 404
        policy = http("GET", "settings", token=token)
        http(
            "PATCH",
            "settings",
            {"upload_limit": 360000},
            token,
            "profile",
            policy["revision"],
            202,
        )
        assert (
            http("GET", "settings", token=token)["defaults"]["upload_limit"] == 360000
        )
        http("POST", "categories", {"name": "fixture"}, token, "add-label", status=202)
        http(
            "PATCH",
            "categories",
            {"name": "fixture", "new_name": "testing"},
            token,
            "rename-label",
            status=202,
        )
        assert "testing" in http("GET", "categories", token=token)["items"]
        http(
            "DELETE",
            "categories",
            {"name": "testing"},
            token,
            "remove-label",
            status=202,
        )
        print(
            "PASS signed gateway scope and replay defense, provider routing, settings and label lifecycle",
            flush=True,
        )
        print(
            "PASS native pairing, token issuance and hostile origin rejection",
            flush=True,
        )
        fixture = os.urandom(512 * 1024)
        seed_dir = work / "seed"
        seed_dir.mkdir()
        (seed_dir / "fixture.bin").write_bytes(fixture)
        storage = lt.file_storage()
        storage.add_file("fixture.bin", len(fixture))
        make = lt.create_torrent(storage, 16384, lt.create_torrent.v1_only)
        make.set_priv(True)
        make.add_tracker(f"http://127.0.0.1:{tracker.server_port}/announce")
        lt.set_piece_hashes(make, str(seed_dir))
        raw = bytes(lt.bencode(make.generate()))
        import base64

        invalid = lt.bdecode(raw)
        invalid[b"info"][b"name"] = b"../escape"
        http(
            "POST",
            "inspections",
            {"metainfo": base64.b64encode(lt.bencode(invalid)).decode()},
            token,
            status=422,
        )
        ins = http(
            "POST",
            "inspections",
            {"metainfo": base64.b64encode(raw).decode()},
            token,
            status=201,
        )
        assert ins["files"][0]["size"] == len(fixture)
        req = {
            "inspection_id": ins["inspection_id"],
            "metadata_revision": 1,
            "selected_file_ids": [0],
            "destination_root_id": "downloads",
        }
        accepted = http("POST", "torrents", req, token, "one-download", status=202)
        assert (
            http("POST", "torrents", req, token, "one-download", status=202) == accepted
        )
        http(
            "POST",
            "torrents",
            {**req, "metadata_revision": 2},
            token,
            "one-download",
            status=409,
        )
        job = "torrents/" + accepted["job_id"]
        http("GET", job, token=other, status=404)
        get = lambda: http("GET", job, token=token)

        def action(verb):
            return http(
                "POST",
                job + "/actions",
                {"action": verb},
                token,
                uuid.uuid4().hex,
                get()["revision"],
                202,
            )

        action("pause")
        eventually(lambda: get()["phase"] == "paused")
        action("resume")
        action("stop")
        eventually(lambda: get()["phase"] == "stopped")
        assert native(op="stop")["enabled"] is False
        native(op="start")
        eventually(lambda: get()["phase"] == "stopped")
        native(op="restart-web")
        eventually(lambda: get()["phase"] == "stopped")
        service.kill()
        service.wait(timeout=12)
        launch()
        eventually(lambda: get()["phase"] == "stopped")
        http(
            "POST",
            job + "/actions",
            {"action": "start"},
            token,
            "wrong-revision",
            99,
            412,
        )
        prefs = {"selected_file_ids": [0], "priorities": {"0": 6}}
        http(
            "PATCH", job + "/files", prefs, token, "prioritize", get()["revision"], 202
        )
        assert http("GET", job + "/files", token=token)["items"][0]["priority"] == 6
        batch = http(
            "POST",
            "batch-operations",
            {
                "action": "stop",
                "jobs": [
                    {"job_id": accepted["job_id"], "revision": get()["revision"]},
                    {"job_id": "missing", "revision": 1},
                ],
            },
            token,
            "batch",
            status=202,
        )
        assert [entry["ok"] for entry in batch["items"]] == [True, False]
        print(
            "PASS web restart, abrupt host recovery, priority, optimistic concurrency and per-item batch results",
            flush=True,
        )
        print(
            "PASS durable replay, owner isolation, pause/resume and stopped state after provider restart",
            flush=True,
        )
        seed_handle = seed.add_torrent(
            {"ti": lt.torrent_info(raw), "save_path": str(seed_dir)}
        )
        eventually(lambda: seed_handle.status().is_seeding)
        action("start")

        def complete():
            s = get()
            if s["phase"] == "failed":
                raise RuntimeError(str(s))
            return s["phase"] == "completed" and s["completed_at"]

        eventually(complete, 75)
        files = list((work / "state" / "downloads").rglob("fixture.bin"))
        assert len(files) == 1 and files[0].read_bytes() == fixture
        print(
            "PASS network transfer: 524288 bytes, independently matched SHA-256",
            hashlib.sha256(fixture).hexdigest(),
            flush=True,
        )
        manifest = http("GET", job + "/manifest", token=token)
        assert (
            manifest["verified"]
            and manifest["files"][0]["sha256"] == hashlib.sha256(fixture).hexdigest()
        )
        action("stop")
        eventually(lambda: get()["phase"] == "stopped")
        move = http(
            "POST",
            job + "/actions",
            {"action": "move", "destination_root_id": "archive"},
            token,
            "move",
            get()["revision"],
            202,
        )
        eventually(
            lambda: http("GET", "operations/" + move["operation_id"], token=token)[
                "phase"
            ]
            == "succeeded"
        )
        manifest = http("GET", job + "/manifest", token=token)
        moved = Path(manifest["output_root"]) / "fixture.bin"
        assert (
            not files[0].exists()
            and moved.read_bytes() == fixture
            and get()["destination_root_id"] == "archive"
        )
        files = [moved]
        print(
            "PASS verified manifest, approved root relocation and durable move receipt",
            flush=True,
        )
        preview = lambda: http(
            "POST",
            "content-deletion-previews",
            {"job_id": accepted["job_id"]},
            token,
            revision=get()["revision"],
            status=201,
        )
        pr = eventually(preview)
        erase = {"preview_id": pr["preview_id"]}
        http("POST", "content-deletions", erase, token, "erase", get()["revision"], 403)
        native(
            op="approve-delete",
            preview_id=pr["preview_id"],
            manifest_digest=pr["manifest_digest"],
        )
        receipt = http(
            "POST", "content-deletions", erase, token, "erase", get()["revision"], 202
        )
        eventually(
            lambda: http("GET", "operations/" + receipt["operation_id"], token=token)[
                "phase"
            ]
            == "succeeded"
        )
        assert not files[0].exists()
        http(
            "DELETE",
            job,
            token=token,
            key="remove",
            revision=get()["revision"],
            status=202,
        )
        http("GET", job, token=token, status=404)
        print("PASS separately authorized file erasure and record removal", flush=True)
        # libtorrent intentionally disables peer metadata exchange on a private torrent.
        # Use a public-format info dictionary inside the same loopback-only transport.
        public = lt.bdecode(raw)
        public[b"info"].pop(b"private", None)
        public_params = lt.add_torrent_params()
        public_params.ti = lt.torrent_info(lt.bencode(public))
        public_params.save_path = str(seed_dir)
        magnet_seed = seed.add_torrent(public_params)
        eventually(lambda: magnet_seed.status().is_seeding)
        magnet = lt.make_magnet_uri(magnet_seed)
        metadata = http("POST", "inspections", {"magnet": magnet}, token, status=201)

        def reviewed():
            value = http("GET", "inspections/" + metadata["inspection_id"], token=token)
            return value if value["phase"] == "ready" else None

        resolved = eventually(reviewed, 60)
        print("PASS magnet metadata resolved from the isolated peer", flush=True)
        assert resolved["files"][0]["path"] == "fixture.bin"
        next_job = http(
            "POST",
            "torrents",
            {**req, "inspection_id": resolved["inspection_id"]},
            token,
            "magnet-download",
            status=202,
        )
        job = "torrents/" + next_job["job_id"]
        assert any(
            t["host"] == "127.0.0.1"
            for t in http("GET", job + "/trackers", token=token)["items"]
        ), "Magnet discovery lost during handoff"
        eventually(complete, 75)
        result = http("GET", job + "/manifest", token=token)
        retained = Path(result["output_root"]) / "fixture.bin"
        assert retained.read_bytes() == fixture
        action("stop")
        eventually(lambda: get()["phase"] == "stopped")
        http(
            "DELETE",
            job,
            token=token,
            key="retain-content",
            revision=get()["revision"],
            status=202,
        )
        assert retained.read_bytes() == fixture
        event_request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/events?after=0",
            headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"},
        )
        with urllib.request.urlopen(event_request, timeout=4) as response:
            assert (
                response.headers.get_content_type() == "text/event-stream"
                and response.readline().startswith(b"id: ")
            )
        print(
            "PASS magnet resolution from a real peer, second download, removal retains bytes, authenticated SSE",
            flush=True,
        )
    finally:
        tracker.shutdown()
        tracker.server_close()
        if service:
            with contextlib.suppress(Exception):
                native(op="stop")
            service.terminate()
            service.wait(timeout=10)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="tlachihuani-swarm-") as directory:
        main(str(Path(sys.argv[1]).resolve()), Path(directory))
