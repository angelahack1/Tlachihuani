"""Run from a verified visible console. Real filesystem publication regressions."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "workers" / "torrent"))
from delivery import Delivery, copy_verified
from storage import Journal, Problem, packed


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / "artifacts" / "verification"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "private"
        self.source.mkdir()
        self.content = b"A real durable publication\n" * 1234
        (self.source / "book.txt").write_bytes(self.content)
        self.entries = [{"id": 0, "path": "book.txt", "size": len(self.content),
                         "sha256": hashlib.sha256(self.content).hexdigest()}]
        self.destination = self.root / "Downloads" / "account" / "job"
        self.destination.parent.mkdir(parents=True)
        self.closing = threading.Event()

    def test_copy_retains_original_and_independently_matches_hash(self):
        result = copy_verified(self.source, self.destination, self.entries, self.closing)
        self.assertEqual((self.destination / "book.txt").read_bytes(), self.content)
        self.assertEqual((self.source / "book.txt").read_bytes(), self.content)
        self.assertEqual(len(result), 1)
        self.assertFalse(list(self.destination.glob("*.part")))

    def test_retry_reuses_identical_existing_file(self):
        first = copy_verified(self.source, self.destination, self.entries, self.closing)
        second = copy_verified(self.source, self.destination, self.entries, self.closing)
        self.assertEqual(first, second)

    def test_changed_user_file_is_never_overwritten(self):
        copy_verified(self.source, self.destination, self.entries, self.closing)
        target = self.destination / "book.txt"
        target.write_bytes(b"user edited this")
        with self.assertRaises(Problem):
            copy_verified(self.source, self.destination, self.entries, self.closing)
        self.assertEqual(target.read_bytes(), b"user edited this")

    def test_corrupt_source_is_never_published(self):
        (self.source / "book.txt").write_bytes(b"broken")
        with self.assertRaises(Problem):
            copy_verified(self.source, self.destination, self.entries, self.closing)
        self.assertFalse((self.destination / "book.txt").exists())
        self.assertFalse(list(self.destination.glob("*.part")))

    def test_cancellation_keeps_original(self):
        self.closing.set()
        with self.assertRaises(InterruptedError):
            copy_verified(self.source, self.destination, self.entries, self.closing)
        self.assertEqual((self.source / "book.txt").read_bytes(), self.content)

    def test_path_escape_is_rejected(self):
        with self.assertRaises(Problem):
            copy_verified(self.source, self.destination, [{**self.entries[0], "path": "../outside"}], self.closing)
        self.assertFalse((self.destination.parent / "outside").exists())

    @unittest.skipUnless(os.name == "nt", "Windows directory junction")
    def test_redirected_account_parent_is_refused_before_any_copy(self):
        import _winapi
        other = self.root / "other"
        (other / "account").mkdir(parents=True)
        link = self.root / "redirect"
        _winapi.CreateJunction(str(other), str(link))
        try:
            with self.assertRaises(Problem):
                copy_verified(self.source, link / "account" / "job", self.entries, self.closing)
            self.assertFalse((other / "account" / "job").exists())
        finally:
            link.rmdir()

    def test_backfill_persists_after_restart_and_reports_removed_output(self):
        journal = Journal(self.root / "state")
        self.addCleanup(journal.db.close)
        journal.db.execute("INSERT INTO jobs(id,owner,metainfo,selection,options,desired,created,completed) VALUES(?,?,?,?,?,?,?,?)",
                           ("j1", "alice", b"metadata", "[0]", "{}", "running", 1, 2))
        row = journal.job("alice", "j1")
        storage = journal.files_root(row)
        storage.mkdir(parents=True)
        (storage / "book.txt").write_bytes(self.content)
        journal.db.execute("INSERT INTO published VALUES(?,?)", ("j1", packed(self.entries)))
        journal.db.execute("INSERT INTO delivery_roots VALUES(?,?,NULL)", ("alice", str(self.root / "Downloads")))
        with ThreadPoolExecutor(max_workers=1) as executor:
            delivery = Delivery(journal, executor, self.closing)
            for _ in range(200):
                delivery.tick([row])
                if delivery.status(row)["delivery_state"] == "saved":
                    break
                time.sleep(.01)
            self.assertEqual(delivery.status(row)["delivery_state"], "saved")
            journal.db.commit()
            recovered = Delivery(journal, executor, self.closing)
            result = recovered.status(row)
            self.assertEqual(result["delivery_state"], "saved")
            (Path(result["saved_to"]) / "book.txt").unlink()
            self.assertEqual(recovered.status(row)["delivery_state"], "failed")
            recovered.tick([row])
            self.assertFalse(recovered.pending, "Do not silently recreate a file the user removed")
            self.assertEqual((storage / "book.txt").read_bytes(), self.content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
