"""Installed-layout check using a private local tracker and a real libtorrent seed."""

import contextlib
import csv
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
    denied_root = None
    sid = None

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
        http("POST", "session-challenges", {}, status=401)
        http("POST", "sessions", {}, status=401)
        token = native(op="issue", profile="delivery-test-" + host_id, scope="read submit control remove erase",
                       application_content_root=str(work / "content_generated"))["body"]["access_token"]
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
            "PASS native account session, retired public routes and hostile origin rejection",
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
        def delivered_manifest():
            result = http("GET", job + "/manifest", token=token)
            if result.get("delivery_state") == "failed":
                raise RuntimeError("Delivery failed: " + str(result.get("delivery_error")))
            return result if result["verified"] else None

        eventually(delivered_manifest)
        manifest = http("GET", job + "/manifest", token=token)
        assert (
            manifest["verified"]
            and manifest["files"][0]["sha256"] == hashlib.sha256(fixture).hexdigest()
        )
        delivered = Path(manifest["output_root"]) / "fixture.bin"
        assert manifest["delivery_state"] == "saved" and delivered.read_bytes() == fixture
        assert manifest["delivery_location"] == "downloads"
        assert "Torrenter" in delivered.parts and str(work / "state") not in str(delivered)
        print("PASS real Windows Downloads delivery:", delivered, flush=True)
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
        moved = Path(manifest["service_output_root"]) / "fixture.bin"
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
        assert not delivered.exists(), "Approved erasure must include the reviewed Downloads copy"
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
        source_path = "inspections/" + metadata["inspection_id"] + "/activity"
        assert http("GET", source_path, token=token)["magnet"] == magnet
        http("GET", source_path, token=other, status=404)

        def reviewed():
            value = http("GET", "inspections/" + metadata["inspection_id"], token=token)
            return value if value["phase"] == "ready" else None

        resolved = eventually(reviewed, 60)
        print("PASS magnet metadata resolved from the isolated peer", flush=True)
        assert resolved["files"][0]["path"] == "fixture.bin"
        # Exercise a real Windows ACL on this run's unique test account leaf.
        # No permissions on the user's Downloads folder or other jobs change.
        if os.name == "nt":
            sid = next(csv.reader([subprocess.check_output(
                ["whoami.exe", "/user", "/fo", "csv", "/nh"], text=True).strip()]))[1]
            primary = delivered.parent.parent
            assert len(primary.name) == 64 and primary.parent.name == "Torrenter" and sid.startswith("S-1-")
            subprocess.run(["icacls.exe", str(primary), "/deny", "*" + sid + ":(AD)"], check=True)
            denied_root = primary
        next_job = http(
            "POST",
            "torrents",
            {**req, "inspection_id": resolved["inspection_id"]},
            token,
            "magnet-download",
            status=202,
        )
        job = "torrents/" + next_job["job_id"]
        audit = http("GET", job + "/activity", token=token)
        assert audit["magnet"] == magnet and audit["source_kind"] == "magnet"
        assert [f["path"] for f in audit["files"] if f["selected"]] == ["fixture.bin"]
        http("GET", job + "/activity", token=other, status=404)
        assert any(
            t["host"] == "127.0.0.1"
            for t in http("GET", job + "/trackers", token=token)["items"]
        ), "Magnet discovery lost during handoff"
        eventually(complete, 75)
        eventually(delivered_manifest)
        result = http("GET", job + "/manifest", token=token)
        retained = Path(result["output_root"]) / "fixture.bin"
        assert retained.read_bytes() == fixture
        if denied_root:
            assert result["delivery_location"] == "content_generated" and result["downloads_error"]
            assert retained.is_relative_to(work / "content_generated" / "Torrenter" / denied_root.name)
            print("PASS actual Windows access denial; verified fallback:", retained,
                  "SHA256", hashlib.sha256(retained.read_bytes()).hexdigest(), flush=True)
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
        # Record removal must retain the user's copy. After proving that contract,
        # clean up only this run's independently checked synthetic fixture.
        assert retained.parent.name == next_job["job_id"]
        assert retained.read_bytes() == fixture
        retained.unlink()
        for empty in (retained.parent, delivered.parent, retained.parent.parent):
            with contextlib.suppress(OSError):
                empty.rmdir()  # Never recurse into a directory in Windows Downloads.
    finally:
        if denied_root is not None:
            subprocess.run(["icacls.exe", str(denied_root), "/remove:d", "*" + sid], check=True)
            with contextlib.suppress(OSError):
                denied_root.rmdir()
        tracker.shutdown()
        tracker.server_close()
        if service:
            with contextlib.suppress(Exception):
                native(op="stop")
            service.terminate()
            service.wait(timeout=10)


if __name__ == "__main__":
    scratch = Path(__file__).resolve().parents[2] / "artifacts" / "verification"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="swarm-") as directory:
        main(str(Path(sys.argv[1]).resolve()), Path(directory))
