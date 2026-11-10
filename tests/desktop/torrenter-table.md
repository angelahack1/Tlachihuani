# Torrenter table regression checks

Run from a verified visible foreground development console. These checks do not
install, restart or modify Windows services. They do not touch either edition's
normal database, account settings or downloads.

```powershell
node --test tests/unit/workspace_table.test.cjs
python tests/desktop/torrenter_table.py --output C:\Development\XAIHT\Tlachihuani\artifacts\verification\table-review --english C:\Development\XAIHT\Tlamatini --spanish C:\Development\XAIHT\Tlamatini-Spanish
```

Use the prepared Python 3.12 development environment with Django, Playwright,
psutil, pywin32 and Shoter's dependencies, a locally installed Chrome, and the
existing `artifacts/jobs-runtime` libtorrent package. No browser or dependency is
downloaded by this test. Keep output outside Windows user profiles.

`table_server.py` serves each checkout's actual workspace views and assets with
Django authentication, CSRF checks and persistent account profiles. Its transport
adapter delegates to the real Jobs API, engine snapshot code and SQLite journal
in process. It deliberately bypasses the installed Windows control pipe. The
isolated journal contains 263 historical QA records for one account and 12 for
another. These are fixture records, **not claimed downloads**. No torrent network
session is started. Ports 19431 and 19432 must be available.

The headed browser checks all twelve data headers in both directions against an
independent Python ordering calculation, keyboard and secondary sorting, search
beyond the first API page, combined filters, invalid ranges, pagination, selection
across pages, view persistence, column hiding/reordering, compact rows, the last
visible-column guard, restored defaults, transfer details and account isolation.
Responsive checks measure actual CSS viewports at 1600, 390 and 320 pixels,
including the footer and settings dialog. Windows display scaling is accounted
for by resizing the browser and asserting the resulting dimensions.

Results and whole-desktop Shoter captures are written to the chosen output folder
with `results.json` and `SUMMARY.html`. Test servers and their dedicated browser
close afterward; the development console remains available for inspection.
This is source workspace integration coverage, not installed-service, release
installation or end-to-end download acceptance.

The canonical assets live in `src/Tlachihuani.Jobs/wwwroot`. Keep the five files
(`workspace.html`, `workspace.css`, `table.js`, `layout.js`, `workspace.js`) identical
to both editions' `Tlamatini/agent/torrenter_workspace` copies. Both Django asset
allowlists and `build_runtime_assets.py` must include every script. Each edition's
normal `npm run lint` now includes this directory.
