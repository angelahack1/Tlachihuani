"""Headed browser acceptance. Uses a private, tracker-free fixture with no remote peers."""

import argparse
import getpass
import os
import re
from urllib.parse import urlparse
import ctypes
from hashlib import file_digest, sha1
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid

from playwright.sync_api import sync_playwright, expect


def eventually(check, seconds=20):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        try:
            result = check()
            if result:
                return result
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Verification deadline expired.")


def foreground_browser():
    api = ctypes.windll.user32
    window = api.GetForegroundWindow()
    kind = ctypes.create_unicode_buffer(256)
    api.GetClassNameW(window, kind, len(kind))
    return (
        api.IsWindowVisible(window)
        and not api.IsIconic(window)
        and kind.value == "Chrome_WidgetWin_1"
    )


def verify_workspace_geometry(page):
    """Measure the real viewport; a footer above spare page space is a failure."""
    box = page.evaluate("""() => {
        const grid=document.querySelector('#transfer-grid');
        return {height:innerHeight,width:innerWidth,
          footer:document.querySelector('footer').getBoundingClientRect().bottom,
          pageWidth:document.body.scrollWidth,
          gridHeight:grid.clientHeight,gridContent:grid.scrollHeight,
          gridWidth:grid.clientWidth,gridContentWidth:grid.scrollWidth,
          selected:document.body.classList.contains('detail-open'),
          rows:document.querySelectorAll('#rows tr').length};
    }""")
    assert abs(box['footer'] - box['height']) <= 2, box
    assert box['pageWidth'] <= box['width'] + 1, box
    if not box['selected'] and box['height'] >= 900 and box['width'] >= 1600 and box['rows'] <= 10:
        assert box['gridContent'] <= box['gridHeight'] + 1, box
        assert box['gridContentWidth'] <= box['gridWidth'] + 1, box
    print('PASS workspace viewport and footer:', json.dumps(box), flush=True)


def verify_saved_downloads(page, username, expected):
    """Verify the signed-in controller's manifests against the current user's actual files."""
    base = page.url.rstrip("/") + "/"
    identity = page.request.get(base + "session/")
    assert identity.ok, identity.status
    identity = identity.json()
    assert identity["username"] == username, "The workspace account changed"
    account = uuid.UUID(identity["profile"]).hex
    headers = {"X-Torrenter-Profile": identity["profile"]}

    def get(route):
        response = page.request.get(base + "api/v1/" + route, headers=headers, max_redirects=0)
        assert response.ok, (route, response.status)
        return response.json()

    folder = (ctypes.c_byte * 16).from_buffer_copy(uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le)
    name = ctypes.c_void_p()
    ctypes.OleDLL("shell32").SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(name))
    try:
        root = Path(ctypes.wstring_at(name)).resolve(strict=True) / "Torrenter" / account
    finally:
        ctypes.windll.ole32.CoTaskMemFree(name)

    complete = []
    cursor = 0
    while True:
        batch = get(f"torrents?limit=250&cursor={cursor}")
        complete.extend(row for row in batch["items"] if row["completed_at"])
        after = batch.get("next_cursor")
        if after is None:
            break
        assert isinstance(after, int) and after > cursor, "Queue cursor did not advance"
        cursor = after
    assert len(complete) == expected, (expected, len(complete))
    checked = 0
    for job in complete:
        job_id = job["job_id"]
        assert re.fullmatch(r"[a-f0-9]{32}", job_id), job_id
        manifest = get(f"torrents/{job_id}/manifest")
        assert manifest.get("verified") and manifest.get("download_verified") and manifest.get("delivery_state") == "saved", (
            job["name"], manifest.get("delivery_state"), manifest.get("delivery_error"))
        directory = Path(manifest["output_root"]).resolve(strict=True)
        assert directory == root / job_id, (directory, root, job_id)
        assert manifest["files"], ("Empty verified manifest", job_id)
        for item in manifest["files"]:
            path = (directory / item["path"]).resolve(strict=True)
            assert path.is_relative_to(directory) and path.is_file(), path
            with path.open("rb") as actual:
                assert os.fstat(actual.fileno()).st_size == item["size"], path
                assert file_digest(actual, "sha256").hexdigest() == item["sha256"], path
            checked += 1
            print("VERIFIED", username, path, item["size"], item["sha256"], flush=True)
    print(f"PASS: {checked} readable files in {len(complete)} completed jobs for {username}: {root}", flush=True)


def check(exe, installed, work, controller, username, verify_completed=None):
    ident = uuid.uuid4().hex
    port = 12064
    service = None
    if not installed:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        service = subprocess.Popen([str(exe), "--console", str(work), ident, str(port)])
    origin = f"http://127.0.0.1:{port}"

    def native(op):
        args = (
            ["--control"] if installed else ["--dev-control", ident, str(service.pid)]
        )
        result = subprocess.run(
            [str(exe), *args],
            input=json.dumps(op) + "\n",
            text=True,
            capture_output=True,
            timeout=25,
            check=True,
        )
        return json.loads(result.stdout)

    try:
        eventually(
            lambda: urllib.request.urlopen(origin + "/api/v1/health", timeout=1).read()
        )
        with sync_playwright() as driver:
            browser = driver.chromium.launch(channel="chrome", headless=False, args=["--start-maximized"])
            try:
                page = browser.new_page(no_viewport=True)
                page.bring_to_front()
                eventually(foreground_browser)
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                if not installed:
                    info = page.request.get(origin + "/controllers")
                    assert info.ok and isinstance(info.json(), list)
                    assert page.request.post(origin + "/api/v1/session-challenges", data={}).status == 401
                    print("PASS private download host discovery and authenticated boundary", flush=True)
                    return
                if urlparse(controller).hostname != "127.0.0.1" or urlparse(controller).scheme != "http":
                    raise ValueError("Use a loopback Tlamatini development server.")
                page.goto(controller.rstrip("/") + "/agent/torrenter/workspace/")
                page.locator("#id_username").fill(username)
                page.locator("#id_password").fill(os.getenv("TLAMATINI_TORRENTER_TEST_PASSWORD") or getpass.getpass("Development account password: "))
                page.locator("form button[type=submit], form input[type=submit]").first.click()
                heading = page.get_by_role("heading", level=1, name=username, exact=True)
                expect(heading).to_be_visible()
                page.reload()
                expect(heading).to_be_visible()
                expect(page.locator('#workspace')).to_be_visible()
                verify_workspace_geometry(page)
                if verify_completed is not None:
                    verify_saved_downloads(page, username, verify_completed)
                    assert not errors, errors
                    return
                expect(page.locator("#transfer-grid thead")).not_to_contain_text(
                    re.compile(r"\b(?:User|Usuario)\b")
                )
                expect(
                    page.get_by_role("button", name="＋ Add torrent")
                ).to_be_visible()
                page.get_by_role("button", name="Columns & view").click()
                page.locator("#column").select_option("2")
                page.get_by_role("button", name="Move right").click()
                page.locator("#table-options").get_by_role("button", name="Done").click()
                verify_workspace_geometry(page)
                print(
                    "PASS headed Chrome: signed-in workspace, refresh and layout preferences",
                    flush=True,
                )
                name = ("tlachihuani-ui-" + ident[:12] + ".bin").encode()
                metainfo = (
                    b"d4:infod6:lengthi8e4:name"
                    + str(len(name)).encode()
                    + b":"
                    + name
                    + b"12:piece lengthi16384e6:pieces20:"
                    + sha1(b"testdata").digest()
                    + b"7:privatei1eee"
                )
                page.get_by_role("button", name="＋ Add torrent").click()
                page.locator("#torrent").set_input_files(
                    {
                        "name": "ui-check.torrent",
                        "mimeType": "application/x-bittorrent",
                        "buffer": metainfo,
                    }
                )
                page.get_by_role("button", name="Inspect metadata").click()
                expect(page.locator("#files")).to_contain_text(name.decode())
                page.get_by_role("button", name="Download selected files").click()
                item = page.get_by_role("button", name=name.decode(), exact=True)
                expect(item).to_be_visible()
                item.click()
                for tab in (
                    "General",
                    "Trackers",
                    "Peers",
                    "HTTP sources",
                    "Content",
                    "Verified output",
                ):
                    page.get_by_role("button", name=tab, exact=True).click()
                    expect(
                        page.get_by_role("button", name=tab, exact=True)
                    ).to_have_attribute("aria-pressed", "true")
                page.get_by_role("button", name="Stop", exact=True).click()
                expect(page.locator("#rows tr").filter(has=item)).to_contain_text(
                    "stopped", timeout=20000
                )
                page.locator("#search").fill("definitely-no-" + ident)
                expect(item).to_have_count(0)
                page.locator("#search").fill("")
                expect(item).to_be_visible()
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="Remove record").click()
                expect(item).to_have_count(0)
                assert not errors, errors
                print(
                    "PASS file upload, all inspectors, stop, filter, record removal and no browser errors",
                    flush=True,
                )
                time.sleep(5)
            finally:
                browser.close()
    finally:
        if service:
            try:
                native({"op": "stop"})
            finally:
                service.terminate()
                service.wait(timeout=15)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--installed", action="store_true")
    parser.add_argument("--controller", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="")
    parser.add_argument("--verify-completed", type=int, metavar="COUNT",
                        help="Verify every file in COUNT existing completed jobs without adding or removing a job.")
    args = parser.parse_args()
    if args.installed and not args.username:
        parser.error("Installed acceptance requires a development account username.")
    if args.verify_completed is not None and (not args.installed or args.verify_completed < 1):
        parser.error("--verify-completed requires --installed and a positive job count.")
    scratch = Path(__file__).resolve().parents[2] / "artifacts" / "verification"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix="workspace-") as work:
        check(args.executable.resolve(), args.installed, Path(work), args.controller, args.username, args.verify_completed)
