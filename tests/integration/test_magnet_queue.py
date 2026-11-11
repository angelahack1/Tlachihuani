"""Exercise FIFO admission, session recovery, and metadata exchange with six real magnets."""
import hashlib
import http.server
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import libtorrent as lt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "workers/torrent"))

from api import Api
from engine import Engine
from storage import Journal, Problem


class MagnetQueueTests(unittest.TestCase):
    def test_six_magnets_resolve_from_a_real_loopback_peer(self):
        scratch = ROOT / "artifacts/verification"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as path:
            seed_dir = Path(path) / "seed"
            seed_dir.mkdir()
            seed = lt.session({"listen_interfaces":"127.0.0.1:0", "enable_dht":False,
                               "enable_lsd":False, "enable_upnp":False, "enable_natpmp":False,
                               "allow_multiple_connections_per_ip":True})
            journal = Journal(Path(path) / "jobs")
            engine = Engine(journal, True)
            class Tracker(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    payload = lt.bencode({b"interval": 1, b"peers": socket.inet_aton("127.0.0.1")
                                          + struct.pack("!H", seed.listen_port())})
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)

                def log_message(self, *args):
                    pass

            tracker = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Tracker)
            serve = threading.Thread(target=tracker.serve_forever, daemon=True)
            serve.start()
            try:
                api = Api(journal, engine)
                token = journal.issue("fixture", "read submit", 300)["access_token"]
                torrents = []
                for n in range(6):
                    name = f"queue-sample-{n}.txt"
                    data = (f"metadata queue fixture {n}\n" * 1024).encode()
                    (seed_dir / name).write_bytes(data)
                    fs = lt.file_storage()
                    fs.add_file(name, len(data))
                    source = lt.create_torrent(fs, 16384, lt.create_torrent.v1_only)
                    source.add_tracker(f"http://127.0.0.1:{tracker.server_port}/announce")
                    lt.set_piece_hashes(source, str(seed_dir))
                    params = lt.add_torrent_params()
                    params.ti = lt.torrent_info(lt.bencode(source.generate()))
                    params.save_path = str(seed_dir)
                    # The fixture must actually serve all six swarms. Libtorrent's
                    # automatic seed queue may pause the sixth completed torrent.
                    params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
                    torrents.append((name, seed.add_torrent(params)))
                end = time.monotonic() + 20
                while not (seed.listen_port() and all(
                    h.status().is_seeding and not h.status().paused for _, h in torrents
                )):
                    self.assertLess(time.monotonic(), end, "Seed did not become ready")
                    time.sleep(.1)
                ids = []
                for n, (_, handle) in enumerate(torrents):
                    uri = lt.make_magnet_uri(handle)
                    code, review = api.dispatch({"method":"POST", "path":"inspections",
                                                 "authorization":"Bearer " + token, "body":{"magnet":uri}})
                    self.assertEqual(code, 201)
                    self.assertEqual(review["lookup_state"], "active" if n < 4 else "queued")
                    ids.append(review["inspection_id"])
                remaining = dict(zip(ids, (name for name, _ in torrents)))
                end = time.monotonic() + 60
                while remaining:
                    engine.tick()
                    for ident, name in list(remaining.items()):
                        review = api.inspection(api.get_inspection("fixture", ident))
                        self.assertNotEqual(review["phase"], "expired", name)
                        if review["phase"] == "ready":
                            self.assertEqual(review["files"][0]["path"], name)
                            del remaining[ident]
                    self.assertLess(time.monotonic(), end, list(remaining.values()))
                    time.sleep(.1)
            finally:
                tracker.shutdown()
                tracker.server_close()
                serve.join()
                engine.close()
                journal.db.close()
                seed.pause()
                del seed

    def test_fifo_restart_timeout_and_invalid_input(self):
        scratch = ROOT / "artifacts/verification"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as path:
            journal = Journal(path)
            engine = Engine(journal, True)
            try:
                api = Api(journal, engine)
                token = journal.issue("one", "read submit", 300)["access_token"]
                def admit(uri):
                    return api.dispatch({"method": "POST", "path": "inspections",
                                         "authorization": "Bearer " + token, "body": {"magnet": uri}})
                ids = []
                for n in range(6):
                    uri = "magnet:?xt=urn:btih:" + hashlib.sha1(str(n).encode()).hexdigest()
                    code, data = admit(uri)
                    self.assertEqual(code, 201)
                    self.assertEqual(data["lookup_state"], "active" if n < 4 else "queued")
                    ids.append(data["inspection_id"])
                with self.assertRaises(Problem) as invalid:
                    admit("bad")
                self.assertEqual(invalid.exception.status, 422)
                with self.assertRaises(Problem):
                    api.get_inspection("another account", ids[-1])
                journal.db.commit()
                engine.close()
                journal.db.close()
                journal = Journal(path)
                engine = Engine(journal, True)
                api = Api(journal, engine)
                journal.db.execute("UPDATE inspections SET expires=0 WHERE pending=1")
                engine.tick()
                self.assertEqual(list(engine.lookups), ids[:4])
                initial_session = engine.sessions["one"]
                discovery = api.dispatch({"method": "GET", "path": "inspections/" + ids[0] + "/activity",
                                          "authorization": "Bearer " + token})[1]["discovery"]
                self.assertIn("connected_peers", discovery)
                self.assertEqual(api.inspection(api.get_inspection("one", ids[5]))["lookup_state"], "queued")
                for i in (0, 2):
                    owner, handle, _ = engine.lookups[ids[i]]
                    engine.lookups[ids[i]] = (owner, handle, 0)
                engine.tick()
                self.assertEqual(list(engine.lookups), [ids[1],ids[3],ids[4],ids[5]])
                self.assertIs(engine.sessions["one"], initial_session)
                self.assertEqual(api.inspection(api.get_inspection("one", ids[0]))["phase"], "expired")
                other_session = engine.session("other")
                for i, (owner, handle, _) in list(engine.lookups.items()):
                    engine.lookups[i] = (owner, handle, 0)
                engine.tick()
                self.assertNotIn("one", engine.sessions)
                self.assertIs(engine.sessions["other"], other_session)
                self.assertIsNot(engine.session("one"), initial_session)
            finally:
                engine.close()
                journal.db.close()


class SessionSettingsTests(unittest.TestCase):
    """Checks the settings without opening a public session (no UPnP traffic in tests)."""

    def test_installed_engine_accepts_incoming_peers(self):
        settings = Engine.session_settings(False)
        self.assertEqual(settings["listen_interfaces"], "0.0.0.0:0")
        for key in ("enable_dht", "enable_upnp", "enable_natpmp", "enable_incoming_utp"):
            self.assertIs(settings[key], True, key)
        self.assertIs(settings["ssrf_mitigation"], True)
        self.assertLessEqual(set(settings), set(lt.default_settings()))

    def test_development_engine_stays_loopback_only(self):
        settings = Engine.session_settings(True)
        self.assertEqual(settings["listen_interfaces"], "127.0.0.1:0")
        for key in ("enable_dht", "enable_upnp", "enable_natpmp", "enable_incoming_utp"):
            self.assertIs(settings[key], False, key)


if __name__ == "__main__":
    unittest.main(verbosity=2)

