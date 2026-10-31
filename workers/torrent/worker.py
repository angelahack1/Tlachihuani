"""Private UTF-8 line protocol inherited from Jobs. EOF terminates the provider."""

import json
import queue
import sys
import threading
import time
import traceback

from api import Api
from engine import Engine
from storage import Journal, Problem


def main():
    if sys.stdin.readline().strip() != "START":
        return
    journal = Journal(sys.argv[1])
    engine = Engine(journal, sys.argv[2] == "development")
    api = Api(journal, engine)
    with journal.db:
        journal.db.execute(
            "UPDATE jobs SET desired='paused',revision=revision+1 WHERE desired='running' AND completed IS NULL AND json_extract(options,'$.resume_on_boot')=0"
        )
    print("READY", flush=True)
    incoming = queue.Queue(4)

    def reader():
        try:
            for line in sys.stdin:
                incoming.put(line)
        finally:
            incoming.put(None)

    threading.Thread(target=reader, daemon=True).start()
    next_tick = 0
    try:
        while True:
            if time.monotonic() >= next_tick:
                with journal.db:
                    api.reconcile_moves()
                    api.reconcile_deletions()
                    engine.tick()
                    api.settle_receipts()
                next_tick = time.monotonic() + 0.3
            try:
                line = incoming.get(timeout=max(0, next_tick - time.monotonic()))
            except queue.Empty:
                continue
            if line is None:
                break
            try:
                with journal.db:
                    status, body = api.dispatch(json.loads(line))
            except Problem as exc:
                status, body = exc.status, {"error": str(exc)}
            except (ValueError, KeyError, TypeError, RuntimeError):
                status, body = 422, {"error": "Invalid request or unsupported torrent."}
            except Exception:
                traceback.print_exc(file=sys.stderr)
                status, body = 500, {"error": "Provider operation failed."}
            print(
                json.dumps({"code": status, "body": body}, allow_nan=False), flush=True
            )
    finally:
        engine.close()
        journal.db.close()


if __name__ == "__main__":
    main()
