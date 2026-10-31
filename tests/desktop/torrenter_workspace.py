"""Headed browser acceptance. Uses a private, tracker-free fixture with no remote peers."""

import argparse
import ctypes
from hashlib import sha1
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


def check(exe, installed, work, tray_pid=None):
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
            browser = driver.chromium.launch(channel="chrome", headless=False)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 850})
                page.bring_to_front()
                eventually(foreground_browser)
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(origin)
                expect(
                    page.get_by_role("heading", name="Torrenter", exact=True)
                ).to_be_visible()
                page.get_by_role("button", name="Request pairing code").click()
                code = page.locator("#code")
                expect(code).to_have_text(__import__("re").compile(r"^\d{8}$"))
                if tray_pid:
                    import importlib.util

                    spec = importlib.util.spec_from_file_location(
                        "xt_pairing", Path(__file__).with_name("xt_pairing.py")
                    )
                    panel = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(panel)
                    panel.approve(tray_pid, code.inner_text())
                    page.bring_to_front()
                else:
                    assert native({"op": "approve", "code": code.inner_text()})["body"][
                        "approved"
                    ]
                expect(
                    page.get_by_role("button", name="＋ Add torrent")
                ).to_be_visible()
                page.get_by_role("button", name="Preferences").click()
                page.locator("#column").select_option("2")
                page.get_by_role("button", name="Move right").click()
                page.locator("#preferences").get_by_role("button", name="Close").click()
                print(
                    "PASS headed Chrome: real pairing, workspace and layout preferences",
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
    parser.add_argument(
        "--tray-pid",
        type=int,
        help="Use the real visible installed XT panel for approval",
    )
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="tlachihuani-browser-") as work:
        check(args.executable.resolve(), args.installed, Path(work), args.tray_pid)
