"""Visible source regressions; real local peers, owned scratch, no installed jobs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import libtorrent as lt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'workers/torrent'))
# The worker is a separately packaged application, not an installed test module.
from api import Api  # noqa: E402
from engine import Engine  # noqa: E402
from storage import Journal, packed  # noqa: E402


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'artifacts/verification')
        self.root = Path(self.temp.name)
        self.journal = Journal(self.root / 'jobs')
        self.engine = Engine(self.journal, True)
        self.api = Api(self.journal, self.engine)

    def tearDown(self):
        self.engine.close()
        self.journal.db.close()
        self.temp.cleanup()

    def job(self, index=0, desired='running', completed=None, snapshot=None, owner='test'):
        payload = (f'Real local transfer {index}\n'.encode() * 4096)
        name = f'book-{index}.txt'
        meta = lt.bencode({b'info': {
            b'name': name.encode(), b'length': len(payload), b'piece length': 16384,
            b'pieces': b''.join(hashlib.sha1(payload[n:n+16384]).digest()
                               for n in range(0, len(payload), 16384)), b'private': 1}})
        ident = f'{index:032x}'
        self.journal.db.execute(
            'INSERT INTO jobs(id,owner,metainfo,selection,options,desired,snapshot,created,completed) VALUES(?,?,?,?,?,?,?,?,?)',
            (ident, owner, bytes(meta), '[0]', packed({'queue_position': index}), desired,
             packed({'name': name, 'selected_bytes': len(payload), 'verified_bytes': 0, **(snapshot or {})}),
             int(time.time()), completed))
        return self.journal.job(owner, ident), payload

    def test_completed_stopped_and_paused_jobs_keep_completion_and_intent(self):
        for index, desired in enumerate(('stopped', 'paused', 'running')):
            row, _ = self.job(index, desired, 123, {'error':'File changed during verification.'})
            state = self.engine.snapshot(row)
            self.assertEqual(state['phase'], 'completed')
            self.assertEqual(state['desired_state'], desired)
            self.assertNotIn('error', state)

    def test_current_failure_is_kept_but_historical_snapshot_error_is_not(self):
        row, _ = self.job(snapshot={'error':'old failure'})
        self.assertNotIn('error', self.engine.snapshot(row))
        self.engine.failures[row['id']] = 'Disk is full'
        self.assertEqual(self.engine.snapshot(row)['error'], 'Disk is full')
        self.assertEqual(self.engine.snapshot(row)['phase'], 'failed')

    @staticmethod
    def quiet_handle():
        handle = MagicMock()
        handle.status.return_value = SimpleNamespace(
            is_finished=False, state='downloading', errc=SimpleNamespace(value=lambda:0),
            total_payload_download=0, download_payload_rate=0)
        return handle

    def test_stalled_slot_yields_only_when_other_work_can_run(self):
        row, _ = self.job()
        queued, _ = self.job(1)
        occupied, _ = self.job(2)
        h = self.quiet_handle()
        self.engine.handles[row['id']] = h
        self.engine.handles[occupied['id']] = self.quiet_handle()
        self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled([row, queued, occupied])
            state = self.engine.snapshot(queued)
        h.pause.assert_called_once()
        self.assertIn(row['id'], self.engine.pending_release)
        self.assertEqual(self.journal.job('test', row['id'])['desired'], 'running')
        self.assertEqual(state['phase'], 'queued')
        self.engine.handles.clear()  # fake handle has no real session

    def test_free_slot_does_not_force_a_stalled_handle_to_disconnect(self):
        row, _ = self.job()
        queued, _ = self.job(1)
        h = self.quiet_handle()
        self.engine.handles[row['id']] = h
        self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled([row, queued])
        h.pause.assert_not_called()
        self.engine.handles.clear()

    def test_stopped_job_does_not_trigger_rotation(self):
        row, _ = self.job()
        stopped, _ = self.job(1, 'stopped')
        h = self.quiet_handle()
        self.engine.handles[row['id']] = h
        self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled([row, stopped])
        h.pause.assert_not_called()
        self.engine.handles.clear()

    def test_host_limit_yields_to_a_different_unsaturated_account(self):
        rows = [self.job(i, owner='first' if i < 2 else 'second')[0] for i in range(4)]
        queued, _ = self.job(4, owner='third')
        handles = [self.quiet_handle() for _ in rows]
        for row, handle in zip(rows, handles):
            self.engine.handles[row['id']] = handle
            self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled([*rows, queued])
        self.assertEqual(sum(h.pause.call_count for h in handles), 1)
        self.assertEqual(len(self.engine.retry_after), 1)
        self.engine.handles.clear()

    def test_checking_and_verifying_are_never_rotated(self):
        rows = [self.job(i)[0] for i in range(3)]
        for index, row in enumerate(rows[:2]):
            handle = self.quiet_handle()
            handle.status.return_value.state = 'checking_files' if index == 0 else 'finished'
            handle.status.return_value.is_finished = index == 1
            self.engine.handles[row['id']] = handle
            self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled(rows)
        self.assertFalse(self.engine.retry_after)
        self.engine.handles.clear()

    def test_slow_progress_does_not_lose_its_slot(self):
        row, _ = self.job()
        queued, _ = self.job(1)
        h = self.quiet_handle()
        h.status.return_value.download_payload_rate = 1
        self.engine.handles[row['id']] = h
        self.engine.progress[row['id']] = (0, 0)
        with patch('engine.time.monotonic', return_value=1000):
            self.engine.rotate_stalled([row, queued])
        h.pause.assert_not_called()
        self.engine.handles.clear()

    def test_verification_waits_for_disk_acknowledgement_and_bounds_wait(self):
        row, _ = self.job()
        h = MagicMock()
        with patch.object(self.engine.publisher, 'submit') as submit:
            self.engine.verify_ready(row, h)
            self.engine.verify_ready(row, h)
            h.pause.assert_called_once()
            submit.assert_not_called()
            self.engine.disk_quiet.add(row['id'])
            self.engine.verify_ready(row, h)
            submit.assert_called_once()
        self.engine.publications.clear()
        self.engine.disk_quiet.clear()
        self.engine.verification_wait[row['id']] = (row['revision'], 0)
        self.engine.verify_ready(row, h)
        self.assertIn('Disk did not finish', self.engine.failures[row['id']])

    def action(self, ident, action):
        row = self.journal.job('test', ident)
        return self.api.change('test', ['torrents', ident, 'actions'], 'POST',
                               {'action':action}, {'revision':f'"{row["revision"]}"'})

    def test_label_revision_during_verification_retains_disk_acknowledgement(self):
        row, _ = self.job()
        handle = MagicMock()
        self.engine.verify_ready(row, handle)
        self.engine.disk_quiet.add(row['id'])
        self.journal.db.execute('UPDATE jobs SET revision=revision+1 WHERE id=?', (row['id'],))
        fresh = self.journal.job('test', row['id'])
        with patch.object(self.engine.publisher, 'submit') as submit:
            self.engine.verify_ready(fresh, handle)
            submit.assert_called_once()
            handle.pause.assert_called_once()
            self.assertEqual(self.engine.publications[row['id']][0], fresh['revision'])
        self.engine.publications.clear()

    def test_recheck_clears_failure_and_retry_without_deleting_partial_files(self):
        row, payload = self.job(desired='stopped')
        root = self.journal.files_root(row)
        root.mkdir(parents=True)
        path = root / 'book-0.txt'
        path.write_bytes(payload[:100])
        self.engine.failures[row['id']] = 'old failure'
        self.engine.retry_after[row['id']] = time.monotonic() + 60
        self.action(row['id'], 'recheck')
        self.assertEqual(path.read_bytes(), payload[:100])
        self.assertNotIn(row['id'], self.engine.failures)
        self.assertNotIn(row['id'], self.engine.retry_after)
        self.assertEqual(self.journal.job('test', row['id'])['desired'], 'running')

    def test_six_real_transfers_two_silent_swarms_cannot_block_four_ready_peers(self):
        self.engine.STALL_SECONDS = .5  # shortened only for this isolated test
        self.engine.RETRY_SECONDS = .2
        seed_root = self.root / 'seed'
        seed_root.mkdir()
        seed = lt.session({'listen_interfaces':'127.0.0.1:0','enable_dht':False,
                           'enable_lsd':False,'enable_upnp':False,'enable_natpmp':False,
                           'allow_multiple_connections_per_ip':True})
        jobs = [self.job(i) for i in range(6)]
        stopped, _ = self.job(6, 'stopped')
        seeds = []
        try:
            for row, payload in jobs[2:]:
                name = json.loads(row['snapshot'])['name']
                (seed_root / name).write_bytes(payload)
                params = lt.add_torrent_params()
                params.ti = lt.torrent_info(row['metainfo'])
                params.save_path = str(seed_root)
                params.flags &= ~(lt.torrent_flags.paused | lt.torrent_flags.auto_managed)
                seeds.append(seed.add_torrent(params))
            end = time.monotonic() + 60
            while not seed.listen_port() or not all(h.status().is_seeding for h in seeds):
                self.assertLess(time.monotonic(), end, 'Local seed did not become ready')
                time.sleep(.1)
            finished = set()
            while len(finished) != 4:
                self.engine.tick()
                self.assertLessEqual(len(self.engine.handles), 2)
                self.assertNotIn(stopped['id'], self.engine.handles)
                for row, payload in jobs[2:]:
                    h = self.engine.handles.get(row['id'])
                    if h:
                        h.connect_peer(('127.0.0.1', seed.listen_port()))
                    fresh = self.journal.job('test', row['id'])
                    if fresh['completed'] and row['id'] not in finished:
                        manifest = self.api.detail(fresh, 'manifest')
                        self.assertTrue(manifest['verified'])
                        saved = Path(manifest['output_root']) / manifest['files'][0]['path']
                        self.assertEqual(saved.read_bytes(), payload)
                        self.assertEqual(hashlib.sha256(saved.read_bytes()).hexdigest(), manifest['files'][0]['sha256'])
                        finished.add(row['id'])
                        print('REAL PEER TRANSFER + HASH PASS:', saved, flush=True)
                self.assertLess(time.monotonic(), end, 'Ready jobs were starved: ' + str(finished))
                time.sleep(.1)
            self.assertTrue(self.journal.db.execute("SELECT 1 FROM events WHERE kind='stalled_retry'").fetchone())
            # Rapid stop/start while resume data is pending must release and reopen.
            ident = jobs[0][0]['id']
            self.action(ident, 'stop')
            self.engine.tick()
            self.action(ident, 'start')
            end = time.monotonic() + 15
            while ident not in self.engine.handles or ident in self.engine.pending_release:
                self.engine.tick()
                self.assertLess(time.monotonic(), end, 'Rapid restart retained a paused handle')
                time.sleep(.1)
            self.assertEqual(self.journal.job('test', stopped['id'])['desired'], 'stopped')
        finally:
            seed.pause()
            for handle in seeds:
                seed.remove_torrent(handle)
            del seed


if __name__ == '__main__':
    unittest.main(verbosity=2)
