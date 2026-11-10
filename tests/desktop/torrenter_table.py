"""Visible English/Spanish table integration checks against isolated real Django/Jobs code.

Use --output outside user profiles. Historical QA records exercise table behavior,
not a torrent download or installed-service certification. Chrome is always headed.
"""

import argparse
from functools import cmp_to_key
import html
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect
import psutil
import win32api
import win32con
import win32gui
import win32process


def run(output, english, spanish):
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(TEMP=str(output), TMP=str(output))
    identities = {}

    def foreground_page(page):
        page.bring_to_front()
        for _ in range(50):
            windows = []
            win32gui.EnumWindows(
                lambda hwnd, _: windows.append(hwnd)
                if win32gui.IsWindowVisible(hwnd)
                else None,
                None,
            )
            for hwnd in windows:
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                try:
                    owned = (
                        pid in identities
                        and psutil.Process(pid).create_time() == identities[pid]
                    )
                except psutil.Error:
                    owned = False
                if not owned or page.title() not in win32gui.GetWindowText(hwnd):
                    continue
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                if win32gui.GetForegroundWindow() != hwnd:
                    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
                    win32api.keybd_event(
                        win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0
                    )
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except OSError:
                        pass
                if win32gui.GetForegroundWindow() == hwnd and not win32gui.IsIconic(
                    hwnd
                ):
                    return hwnd
            page.wait_for_timeout(100)
        raise RuntimeError("Owned headed Chrome is not in front; verification stopped.")

    runtime = output / "shoter-runtime"
    runtime.mkdir(exist_ok=True)
    shutil.copy2(
        english / "Tlamatini/agent/agents/shoter/shoter.py", runtime / "shoter.py"
    )
    spec = importlib.util.spec_from_file_location("table_shoter", runtime / "shoter.py")
    shoter = importlib.util.module_from_spec(spec)
    previous = Path.cwd()
    try:
        spec.loader.exec_module(shoter)
    finally:
        os.chdir(previous)
    result = {
        "status": "RUNNING",
        "headless": False,
        "scope": "Source workspace; isolated historical QA rows; real Django auth and Jobs API/journal",
        "checks": [],
    }
    errors = []

    def persist():
        (output / "results.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        cards = "".join(
            "<article><h2>"
            + html.escape(c["name"])
            + "</h2>"
            + ('<img src="' + c["image"] + '">' if c.get("image") else "")
            + "</article>"
            for c in result["checks"]
        )
        (output / "SUMMARY.html").write_text(
            '<!doctype html><meta charset="utf-8"><title>Torrenter table verification</title>'
            "<style>body{font:17px system-ui;background:#101e27;color:#e5f2ed;max-width:1200px;margin:40px auto;padding:20px}h1,h2{color:#7bd9c7}article{padding:12px;border-bottom:1px solid #36515a}img{width:100%}</style>"
            "<h1>Torrenter workspace · "
            + result["status"]
            + "</h1><p>"
            + html.escape(result["scope"])
            + "</p>"
            + cards,
            encoding="utf-8",
        )

    def passed(page, name, photo=False):
        foreground_page(page)
        item = {"name": name}
        if photo:
            filename = f"{len(result['checks']) + 1:02}.png"
            shoter.capture_screenshot(str(output), all_screens=True, filename=filename)
            page.screenshot(path=str(output / ("page-" + filename)))
            item["image"] = filename
        result["checks"].append(item)
        print("PASS", name, flush=True)
        persist()

    def stream(proc, edition):
        with (output / (edition + "-server.log")).open(
            "w", encoding="utf-8"
        ) as logfile:
            for line in proc.stdout:
                logfile.write(line)
                logfile.flush()
                if "GET /agent/" not in line:
                    print("[" + edition + "]", line.strip(), flush=True)

    def natural(value):
        return [
            (1, int(x)) if x.isdigit() else (0, x.casefold())
            for x in re.split(r"(\d+)", value)
        ]

    def compare(a, b, direction):
        if isinstance(a, tuple):
            return next((n for x, y in zip(a, b) if (n := compare(x, y, direction))), 0)
        if a is None or b is None:
            return (a is None) - (b is None)
        if isinstance(a, str):
            a, b = natural(a), natural(b)
        return direction * ((a > b) - (a < b))

    def status(row):
        return (
            "Service update required"
            if row["completed_at"] and row["delivery_state"] == "service_store"
            else row["phase"]
        )

    getters = {
        "name": lambda r: r["name"],
        "selected_bytes": lambda r: r["selected_bytes"],
        "progress": lambda r: 100 * r["verified_bytes"] / r["selected_bytes"],
        "phase": status,
        "seeds": lambda r: (r["seeds"], r["peers"]),
        "download_rate_bps": lambda r: r["download_rate_bps"],
        "upload_rate_bps": lambda r: r["upload_rate_bps"],
        "eta_seconds": lambda r: r["eta_seconds"],
        "ratio": lambda r: r["ratio"],
        "availability": lambda r: r["availability"],
        "queue_position": lambda r: r["queue_position"],
        "completed_at": lambda r: r["completed_at"],
    }

    def order(page):
        return page.locator("#rows tr[data-job-id]").evaluate_all(
            "(rows)=>rows.map(r=>r.dataset.jobId)"
        )

    def login(page, base, username="table-review"):
        # Deliberately truncate one read-only session response to pin bounded
        # recovery. Mutation requests are never intercepted or retried here.
        page.route('**/workspace/session/', lambda route: route.fulfill(status=200, content_type='application/json', body=''), times=1)
        page.goto(base + "/login/?next=/agent/torrenter/workspace/")
        foreground_page(page)
        page.locator("#id_username").fill(username)
        page.locator("#id_password").fill("Workspace-test-only-2026")
        with page.expect_response(
            lambda response: "/login/" in response.url
            and response.request.method == "POST"
        ) as submitted:
            page.get_by_role("button", name="Sign in", exact=True).click()
        assert submitted.value.status == 302, page.locator("form").inner_text()
        expect(page.locator("#workspace-owner")).to_have_text(username)
        expect(page.locator("#count")).to_have_text(
            "263 of 263 downloads"
            if username == "table-review"
            else "12 of 12 downloads"
        )
        page.locator("#show-columns").click()
        page.locator("#reset-view").click()
        page.locator("#table-options").get_by_role(
            "button", name="Done", exact=True
        ).click()

    try:
        with sync_playwright() as driver:
            context = driver.chromium.launch_persistent_context(
                str(output / "chrome-profile"),
                channel="chrome",
                headless=False,
                viewport={"width": 1600, "height": 1000},
                args=["--no-first-run", "--disable-background-networking"],
            )
            profile_path = str(output / "chrome-profile").casefold()
            for proc in psutil.process_iter(["pid", "create_time", "cmdline"]):
                if any(
                    profile_path in arg.casefold() for arg in proc.info["cmdline"] or []
                ):
                    identities[proc.pid] = proc.info["create_time"]
            page = context.pages[0]
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on('requestfailed', lambda req: print('BROWSER REQUEST FAILED:', req.method, req.url, req.failure, flush=True))
            def finished(request):
                if request.url.endswith('/session/') or '/actions' in request.url:
                    response = request.response()
                    print('BROWSER TRANSPORT:', request.method, request.url, response.status,
                          'body bytes', len(response.body()), flush=True)
            page.on('requestfinished', finished)
            try:
                for repo, port in ((english, 19431), (spanish, 19432)):
                    edition = repo.name
                    proc = subprocess.Popen(
                        [
                            sys.executable,
                            "-u",
                            str(Path(__file__).with_name("table_server.py")),
                            "--repo",
                            str(repo),
                            "--state",
                            str(output / edition),
                            "--port",
                            str(port),
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        creationflags=0,
                    )
                    threading.Thread(
                        target=stream, args=(proc, edition), daemon=True
                    ).start()
                    base = f"http://127.0.0.1:{port}"
                    try:
                        for _ in range(80):
                            if proc.poll() is not None:
                                raise RuntimeError(edition + " test server exited")
                            try:
                                urllib.request.urlopen(
                                    base + "/login/", timeout=1
                                ).close()
                                break
                            except OSError:
                                time.sleep(0.5)
                        else:
                            raise RuntimeError("Server startup timeout")
                        page.set_viewport_size({"width": 1600, "height": 1000})
                        login(page, base)
                        # Exercise real source UI -> authenticated Django -> Jobs
                        # mutations on isolated QA rows, never installed downloads.
                        page.get_by_role('button', name='QA Atlas 1 — résumé.pdf', exact=True).click()
                        expect(page.locator('[data-action="start"]')).to_be_disabled()
                        expect(page.locator('[data-action="cancel"]')).to_be_disabled()
                        expect(page.locator('[data-action="recheck"]')).to_be_enabled()
                        page.locator('[data-tab="files"]').click()
                        expect(page.get_by_role('button', name='Save file selection', exact=True)).to_be_enabled()
                        page.locator('[data-tab="trackers"]').click()
                        expect(page.get_by_role('button', name='Replace source list…', exact=True)).to_be_visible()
                        page.locator('[data-tab="general"]').click()
                        passed(page, edition + ' · session recovers one empty response; completed downloads cannot be started or cancelled again', True)
                        page.get_by_role('button', name='QA Atlas 3 — résumé.pdf', exact=True).click()
                        recovery_row = page.locator('#rows tr').filter(has=page.get_by_role('button', name='QA Atlas 3 — résumé.pdf', exact=True))
                        expect(page.locator('[data-action="start"]')).to_be_enabled()
                        page.locator('[data-action="start"]').click()
                        expect(page.locator('#message')).to_contain_text('Request recorded')
                        expect(recovery_row).to_contain_text('queued')
                        expect(page.locator('[data-action="start"]')).to_be_disabled()
                        page.locator('[data-action="stop"]').click()
                        expect(recovery_row).to_contain_text('stopped')
                        passed(page, edition + ' · stopped partial download Start / Stop reaches the real Jobs API', True)
                        page.get_by_role('button', name='QA Atlas 5 — résumé.pdf', exact=True).click()
                        recovery_row = page.locator('#rows tr').filter(has=page.get_by_role('button', name='QA Atlas 5 — résumé.pdf', exact=True))
                        expect(recovery_row).to_contain_text('failed')
                        expect(page.locator('[data-action="start"]')).to_be_disabled()
                        expect(page.locator('[data-action="recheck"]')).to_be_enabled()
                        page.locator('[data-action="recheck"]').click()
                        expect(recovery_row).to_contain_text('queued')
                        expect(page.locator('#details')).not_to_contain_text('QA disk verification failure')
                        page.locator('[data-action="stop"]').click()
                        expect(recovery_row).to_contain_text('stopped')
                        passed(page, edition + ' · failed download Recheck clears the actual engine error', True)
                        page.locator('#clear-filters').click()
                        identity = page.request.get(
                            base + "/agent/torrenter/workspace/session/"
                        ).json()
                        rows = []
                        cursor = 0
                        while cursor is not None:
                            reply = page.request.get(
                                base
                                + f"/agent/torrenter/workspace/api/v1/torrents?limit=250&cursor={cursor}",
                                headers={"X-Torrenter-Profile": identity["profile"]},
                            )
                            assert reply.ok, reply.text()
                            batch = reply.json()
                            rows.extend(batch["items"])
                            cursor = batch["next_cursor"]
                        assert len(rows) == 263
                        assert page.locator("th button[data-sort]").count() == 12
                        assert (
                            page.locator("th").first.locator("[data-sort]").count() == 0
                        )
                        page.locator("#page-size").select_option("0")
                        expect(page.locator("#rows tr")).to_have_count(263)
                        for key, getter in getters.items():
                            for _ in range(2):
                                header = page.locator(f'[data-sort="{key}"]')
                                foreground_page(page)
                                header.click()
                                direction = (
                                    1
                                    if header.locator("..").get_attribute("aria-sort")
                                    == "ascending"
                                    else -1
                                )
                                expected = sorted(
                                    rows,
                                    key=cmp_to_key(
                                        lambda a, b: compare(
                                            getter(a), getter(b), direction
                                        )
                                        or compare(a["job_id"], b["job_id"], 1)
                                    ),
                                )
                                assert order(page) == [r["job_id"] for r in expected], (
                                    edition,
                                    key,
                                    direction,
                                )
                            passed(
                                page, edition + " · " + key + " ascending / descending"
                            )
                        page.locator('[data-sort="name"]').focus()
                        page.keyboard.press("Enter")
                        expect(page.locator('[data-sort="name"]')).to_be_focused()
                        page.locator('[data-sort="selected_bytes"]').click(
                            modifiers=["Shift"]
                        )
                        expect(page.locator("#sort-summary")).to_contain_text("Name")
                        expect(page.locator("#sort-summary")).to_contain_text("Size")
                        passed(
                            page,
                            edition + " · keyboard sorting, multi-column priority",
                            True,
                        )
                        page.locator("#search").fill("résumé " + rows[-1]["job_id"])
                        expect(page.locator("#rows tr")).to_have_count(1)
                        expect(page.locator("#rows")).to_contain_text("Atlas 263")
                        page.locator("#clear-filters").click()
                        page.locator("#category").select_option("Science")
                        page.locator("#tag").select_option("odd")
                        page.locator("#tracker").select_option("qa.invalid")
                        page.locator("#progress-min").fill("20")
                        page.locator("#progress-max").fill("40")
                        expected = {
                            r["job_id"]
                            for r in rows
                            if r["category"] == "Science"
                            and 20
                            <= 100 * r["verified_bytes"] / r["selected_bytes"]
                            <= 40
                        }
                        assert set(order(page)) == expected
                        page.locator("#progress-min").fill("90")
                        expect(page.locator("#filter-error")).to_contain_text(
                            "From no greater"
                        )
                        expect(page.locator("#rows")).to_contain_text("No matching")
                        page.locator("#clear-filters").click()
                        passed(
                            page,
                            edition
                            + " · global search beyond row 250, combined filters and invalid range",
                        )
                        page.locator("#page-size").select_option("25")
                        page.locator("#select-page").check()
                        expect(page.locator("#selection-count")).to_have_text(
                            "25 selected"
                        )
                        page.locator("#page-next").click()
                        expect(page.locator("#selection-count")).to_contain_text(
                            "25 outside this page"
                        )
                        page.locator("#rows input").first.check()
                        expect(page.locator("#selection-count")).to_contain_text(
                            "26 selected"
                        )
                        page.locator("#page-last").click()
                        expect(page.locator("#rows tr")).to_have_count(13)
                        expect(page.locator("#page-summary")).to_have_text(
                            "251–263 of 263"
                        )
                        page.locator("#clear-selection").click()
                        passed(
                            page,
                            edition
                            + " · pagination, select page and selection across pages",
                            True,
                        )
                        page.locator("#show-columns").click()
                        page.locator('[data-column-toggle="1"]').uncheck()
                        page.locator('[data-column-toggle="2"]').uncheck()
                        page.locator("#compact-rows").check()
                        page.locator("#column").select_option("3")
                        page.locator("#col-left").click()
                        page.locator("#table-options").get_by_role(
                            "button", name="Done", exact=True
                        ).click()
                        expect(page.locator('th[data-column="1"]')).to_be_hidden()
                        expect(page.locator('th[data-column="2"]')).to_be_hidden()
                        page.reload()
                        expect(page.locator("#count")).to_have_text(
                            "263 of 263 downloads"
                        )
                        expect(page.locator('th[data-column="1"]')).to_be_hidden()
                        expect(page.locator("#page-size")).to_have_value("25")
                        assert page.locator("body").evaluate(
                            '(e)=>e.classList.contains("compact-rows")'
                        )
                        page.locator("#show-columns").click()
                        passed(
                            page,
                            edition
                            + " · saved column visibility, order, density, page size and sorting",
                            True,
                        )
                        page.locator("#reset-view").click()
                        for index in range(2, 13):
                            page.locator(f'[data-column-toggle="{index}"]').uncheck()
                        expect(
                            page.locator('[data-column-toggle="1"]')
                        ).to_be_disabled()
                        page.locator("#reset-view").click()
                        page.locator("#table-options").get_by_role(
                            "button", name="Done", exact=True
                        ).click()
                        page.locator("#rows tr").first.press("Enter")
                        expect(page.locator("body")).to_have_class(
                            re.compile("detail-open")
                        )
                        expect(page.locator("#selected")).to_contain_text("QA Atlas")
                        passed(
                            page,
                            edition
                            + " · last-column guard, restore defaults, keyboard transfer details",
                        )
                        for width, height in ((1600, 1000), (390, 844), (320, 740)):
                            page.set_viewport_size({"width": width, "height": height})
                            foreground_page(page)
                            # Reconcile Chromium's device viewport with real CSS pixels
                            # under Windows display scaling. Assert the measured viewport
                            # afterwards; never mistake an oversized layout for mobile.
                            for _ in range(4):
                                actual = page.evaluate(
                                    "({width:innerWidth,height:innerHeight})"
                                )
                                if (
                                    abs(actual["width"] - width) <= 1
                                    and abs(actual["height"] - height) <= 1
                                ):
                                    break
                                viewport = page.viewport_size
                                page.set_viewport_size(
                                    {
                                        "width": round(
                                            viewport["width"] * width / actual["width"]
                                        ),
                                        "height": round(
                                            viewport["height"]
                                            * height
                                            / actual["height"]
                                        ),
                                    }
                                )
                                page.wait_for_timeout(150)
                            geometry = page.evaluate("""() => ({width:innerWidth,content:document.body.scrollWidth,height:innerHeight,
                                footer:document.querySelector('footer').getBoundingClientRect().bottom})""")
                            assert geometry["content"] <= width + 1, geometry
                            assert abs(geometry["width"] - width) <= 1, geometry
                            assert abs(geometry["footer"] - height) <= 2, geometry
                            page.locator("#show-columns").click()
                            rect = page.locator("#table-options").bounding_box()
                            assert (
                                rect["x"] >= 0
                                and rect["x"] + rect["width"] <= width + 1
                            ), rect
                            passed(
                                page,
                                edition
                                + f" · {width}px viewport and accessible view dialog",
                                True,
                            )
                            page.locator("#table-options").get_by_role(
                                "button", name="Done", exact=True
                            ).click()
                        page.set_viewport_size({"width": 1600, "height": 1000})
                        page.locator("#show-columns").click()
                        page.locator('[data-column-toggle="2"]').uncheck()
                        page.locator("#table-options").get_by_role(
                            "button", name="Done", exact=True
                        ).click()
                        # Normal password login as another account: no forged cookies or sessions.
                        page.goto(base + "/login/?next=/agent/torrenter/workspace/")
                        page.locator("#id_username").fill("table-other")
                        page.locator("#id_password").fill("Workspace-test-only-2026")
                        page.get_by_role("button", name="Sign in", exact=True).click()
                        try:
                            expect(page.locator("#count")).to_have_text(
                                "12 of 12 downloads"
                            )
                        except AssertionError:
                            print(
                                "Account load diagnostics:",
                                page.locator("#message").inner_text(),
                                page.evaluate("({...localStorage})"),
                                flush=True,
                            )
                            page.screenshot(
                                path=str(output / "account-load-failure.png")
                            )
                            raise
                        expect(page.locator('th[data-column="2"]')).to_be_visible()
                        passed(
                            page,
                            edition
                            + " · separate accounts retain separate queues and views",
                            True,
                        )
                        assert not errors, errors
                    except BaseException:
                        print('VISIBLE FAILURE STATUS:', page.locator('#message').inner_text(), flush=True)
                        page.screenshot(path=str(output / (edition + '-failure.png')))
                        raise
                    finally:
                        proc.terminate()
                        proc.wait(timeout=15)
                result["status"] = "PASS"
                result["page_errors"] = errors
                persist()
                page.goto((output / "SUMMARY.html").as_uri())
                foreground_page(page)
                time.sleep(8)
            finally:
                context.close()
    except BaseException as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)
        result["page_errors"] = errors
        persist()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--english", type=Path, required=True)
    parser.add_argument("--spanish", type=Path, required=True)
    args = parser.parse_args()
    run(args.output, args.english, args.spanish)
