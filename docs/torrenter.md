# Operating Torrenter

Torrenter downloads selected files in the independent Windows service `Tlachihuani.Jobs`. The XT tray, browser and original `Tlachihuani` service have separate lifetimes. Closing a window releases its UI session. Windows owns the download host under `NT SERVICE\Tlachihuani.Jobs`.

## Open the workspace

1. Right-click **XT → Start Services**. When XT turns color, the Torrenter API is ready. **Show panel → Services…** shows Jobs, engine and web readiness, the active transfer count and the number of job records. Choose **XT → Stop Services** to stop the entire Tlachihuani stack and leave the gray tray icon running.
2. Choose **Open workspace** in XT or **Panels → Torrenter Workspace** in Tlamatini. Sign in to Tlamatini once. When both editions are available, XT lets you choose the account to view. Reloading keeps that session.
3. Choose **Add torrent**, upload a `.torrent` or enter a magnet, then **Inspect metadata**. Choose files, priorities, destination, resume and seeding policy. **Download selected files** creates the durable job.
4. Search and filter the queue, then choose **Columns & view** to customize its display (see below). Use the transfer’s **Verified output** tab to see its output directory and per-file SHA-256. **Stop** retains partial files until you choose **Start**. **Pause** pairs with **Resume**. **Cancel** ends the transfer permanently. **Remove record** retains files. **Erase files…** requires a separate exact-file review and approval in XT.

### Sort and personalize the download table

- Click any of the twelve data headers to switch between ascending and descending order. **Select** is fixed and never sortable. Arrows show direction; **Shift-click** adds another sorting priority. **Reset sorting** restores Name ascending. Size, progress, rates, ETA, ratio, availability, queue position and dates sort by their actual values, not formatted strings; unknown values stay last. Seeds / peers compares seeds first, then peers.
- Search combines all entered words across names, categories, tags, tracker hosts, output paths and job IDs. Combine it with status, category, tag, tracker, activity and inclusive progress-percentage filters. **Clear filters** restores the complete queue.
- **Columns & view** hides/shows columns, changes their order and minimum width, enables compact rows and adjusts the details pane. Select remains visible and at least one data column stays available. Views, sorting and page size are saved separately for each signed-in account in this browser. **Restore default view** resets display preferences; it does not change jobs.
- Choose 25, 50, 100, 250 or **All** rows. The workspace reads every API page before sorting and filtering, including transfers beyond the first 250. A failed later page preserves the previous complete view and reports the connection error.
- The header checkbox selects only the current page. Selection remains when filtering, sorting or paging; the selection banner explicitly counts selected transfers outside the current page. **Clear selection** clears all checks. Row clicks or Enter open details even when Name is hidden. **Preferences** continues to control account transfer defaults, independently of table display.

**Restart web** restarts the HTTP process independently of active peers. **Stop provider** drains Torrenter and persists the stop across Jobs restarts. **Stop Jobs** stops the entire provider host. Use **Start Jobs** and, if explicitly stopped, **Start provider** to bring it back.

Open the [workspace](http://127.0.0.1:12064/) or [API discovery](http://127.0.0.1:12064/api/v1). This deployment binds the dashboard to IPv4 loopback. Torrent traffic uses a separate peer socket.

## Windows installation

For a new graphical installation, follow the [installer and uninstaller guide](../packaging/setup/README.md). It installs both the primary service and Jobs. The following PowerShell instructions apply to script-managed deployments.

Use a verified visible foreground PowerShell console in the source checkout. Windows x64 requires the .NET 10 ASP.NET Core and Desktop shared runtimes. The pinned .NET SDK supplies both on the development machine.

```powershell
Set-Location -LiteralPath 'C:\Development\XAIHT\Tlachihuani'
.\scripts\Build.ps1 -Mode Check
.\scripts\Build.ps1 -Mode Publish
```

For a first installation, run the following from an elevated foreground console. Use the Windows user who will operate XT. Exit an existing installed tray before an update that replaces it.

```powershell
.\packaging\windows\Install-Jobs.ps1 -OperatorAccount ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -UpdateTray
```

For an existing Jobs installation, run `.\packaging\windows\Update-Jobs.ps1 -UpdateTray` after publishing. It stages and swaps the program directories, retains the previous generation, preserves the installation identity and journal, and checks the native host when restoring a running service. `Unregister-Jobs.ps1` removes the verified Jobs SCM registration and retains data.

Run the tray and these status checks as the delegated operator in an ordinary PowerShell window. The executable accepts one JSON request on standard input.

```powershell
$base = Join-Path $env:ProgramFiles 'XAIHT\Tlachihuani'
Start-Process -FilePath (Join-Path $base 'Tray\Tlachihuani.Tray.exe') -ArgumentList '--show'
Get-Service Tlachihuani,Tlachihuani.Jobs
'{"op":"catalog"}' | & (Join-Path $base 'Jobs\Tlachihuani.Jobs.exe') --control | ConvertFrom-Json
Invoke-RestMethod 'http://127.0.0.1:12064/api/v1/health'
```

To enable XT on future logins, run `.\packaging\windows\Set-TrayStartup.ps1` as the intended Windows user. Both services remain Manual; opening XT at sign-in does not start them. The operator chooses **Start Services**.

## REST contract for the browser and wrapped agent

Use the API prefix `/api/v1`. For automation, select **Issue API credential** in XT or enroll a trusted gateway through the native pipe. Scopes are `read`, `submit`, `control`, `remove` and `erase`. Send credentials as `Authorization: Bearer <token>`. Job IDs and receipts belong to the issuing account. Direct tokens expire after one hour, paired browser tokens after 30 minutes and gateway-issued tokens after five minutes.

| Intent | Request | Result |
|---|---|---|
| Discover | GET `/`, `/health`, authenticated `/capabilities` | Protocol, engine readiness, scopes, approved roots and verbs |
| Inspect | POST `/inspections` with multipart field `file` or JSON `{"magnet":"magnet:…"}`. GET `/inspections/{id}` | HTTP 201 admits the magnet even when all four metadata slots are busy. Poll the same inspection ID; submit files only after `phase: ready`. |
| Submit | POST `/torrents` with `inspection_id`, `metadata_revision`, `selected_file_ids`, optional `priorities` keyed by file ID, and `destination_root_id` | HTTP 202 returns job ID, revision and durable operation ID |
| Observe | GET `/torrents?limit=100&cursor=0`, `/torrents/{id}`, `/operations/{id}` | Queue, desired and observed state, selected/verified bytes and saved outcome. List queries accept search, phase, desired, category, tag, tracker, sort and direction |
| Inspect a transfer | GET `/torrents/{id}/{files,trackers,peers,web-seeds,statistics,manifest}` | File selection, redacted source hosts, live peer information or verified publication |
| Change state | POST `/torrents/{id}/actions` with `action` | `pause`, `resume`, `stop`, `start`, `cancel`, `recheck`, `reseed` or `move`. Move also requires `destination_root_id` and a stopped job |
| Bulk control | POST `/batch-operations` with `action` and `jobs: [{job_id,revision}]` | One receipt with per-job successes and errors |
| Edit | PATCH `/torrents/{id}` or `/files`, `/trackers`, `/web-seeds` beneath that job | Labels, queue position, rate limits and policy. Stop first to change selection/priorities or replace source URL lists |
| Remove | DELETE `/torrents/{id}` | Removes the visible record and retains the bytes |
| Erase | POST `/content-deletion-previews`, native approval, then POST `/content-deletions` | Exact paths, sizes and file identities are checked again. Poll the operation for the outcome |
| Labels and defaults | GET/POST/PATCH/DELETE `/categories`, `/tags`. GET/PATCH `/settings`. GET `/statistics` | Owned collections and validated account defaults. A label change never removes files |
| Events | GET `/events?after={cursor}`, optionally `Accept: text/event-stream` | JSON events or authenticated SSE. On 410 fetch a fresh queue and use its event cursor |

Use a unique `Idempotency-Key` for each durable mutation. Send `If-Match: "N"` for an individual job’s current revision, the deletion preview/commit, or a settings edit. A repeated identical mutation returns its original admission receipt. Poll its operation ID to distinguish acceptance, success, supersession and failure. A 412 requires a fresh read. A conflict on reuse of an idempotency key requires checking the original payload. Batch revisions travel with each item. Label requests use `name` and, when renaming, `new_name`. File selection accepts priorities 1–7 for selected indexes.

Trusted application enrollment uses native `{"op":"issue","gateway":true,"profile":"<application account>","scope":"read submit control"}`. Protect the returned signing key in the client’s credential store. Exchange an assertion at `POST /sessions/delegated` with `gateway_id`, `account`, `nonce`, `expires` (Unix seconds) and `signature`. Sign the UTF-8 bytes of Python-compatible compact JSON for `[gateway_id,account,"Tlachihuani.Torrenter",nonce,expires]` with HMAC-SHA256 using the UTF-8 signing key and lowercase hex output. The server checks the enrolled account, the single-use nonce and a maximum 90-second assertion window. The resulting token inherits the enrollment scopes. **Revoke access** in XT invalidates the operator’s sessions and enrollments. The Tlamatini wrapper belongs in a separately authorized Tlamatini change.

## Ownership and recovery

### Stalled queues and verification (source correction, 10 November 2026)

The two-per-account/four-per-host limits are unchanged. After 180 seconds without
payload progress, an unfinished running transfer yields only when other eligible
queued work is blocked. It retains partial data and running intent, waits at least
60 seconds and retries behind waiting work. The snapshot reports `phase: queued`,
`queue_reason: stalled_retry` and `retry_in_seconds`; the journal records
`stalled_retry`. No timer changes user-paused or user-stopped jobs. No-progress
rotation excludes checking, verifying and completed/seeding transfers, and does not
disconnect a stalled transfer when the waiting job can already use a free slot.

Publication waits for [`torrent_paused_alert`](https://libtorrent.org/reference-Alerts.html#torrent_paused_alert)
before hashing: `pause()` itself is asynchronous. A missing disk acknowledgment becomes an explicit recoverable error
after 60 seconds. Recheck clears the failure and validates the retained pieces;
successful publication clears obsolete errors. Completed jobs retain their
completion even when the peer session's desired state is stopped. Actual errors
and delivery failures remain visible. Rapid Stop/Start finishes releasing the old
handle before reopening it rather than leaving a paused handle occupying a slot.
Label/revision edits during hashing retain the disk-pause acknowledgment.

The two Tlamatini clients normalize historical completed/stopped snapshots, label
obsolete errors as `previous_error`, expose recovery guidance and restrict workspace
actions to eligible selections. Scheduler and disk synchronization changes belong
to Jobs and require a separate service update. No build or installation was run for
this source correction; the live queue was inspected without changing its jobs.

Run `tests/integration/test_transfer_recovery.py` visibly for the real local-peer
starvation/restart regression, then the existing magnet and delivery suites.
`tests/desktop/torrenter_table.py` drives both editions' real source workspace and
authenticated Jobs API against isolated QA records, with headed Chrome. Its UI
records are not evidence of downloading; the peer suite supplies that evidence.
The 10 November run passed 64 automated checks and 48 headed-browser checks across
both editions. Four real local-peer payloads completed despite two silent swarms.
An independent read-only installed audit matched all 432 delivered files from 21
completed downloads. Evidence is under
`artifacts/verification/torrenter-state-20261110/`; the installed service and its
three unfinished downloads were left unchanged.

### Windows Downloads publication (1 November 2026)

The local controller prepares the operator's real Windows Downloads known folder
before issuing an account credential. It creates only a dedicated
`Torrenter/<account profile>` directory and grants the Jobs service Modify there.
The identification-only pipe is unchanged: the service validates the authenticated
caller's ownership and account folder name. The controller checks for reparse
points while preparing the folder. The service opens the account directory and
checks its final Windows path; it needs no permission to list the parent
`Downloads\Torrenter` or the rest of the user's Downloads. The worker checks the
destination again before copying. The private journal and service working
directories remain protected.

Jobs automatically copies each completed, hash-verified selection into that folder,
under its job ID, and publishes each file atomically. The service retains its
working copy; closing either Tlamatini or the browser does not interrupt delivery.
Previously completed jobs are backfilled after that account connects. Existing
files with different content are preserved and reported as a delivery failure.
Successful delivery is persisted across service restarts. A user-modified or
removed delivered file is reported, rather than silently recreated on every poll.

Status includes `delivery_state`, `saved_to` and `delivery_error`. A registered
account's manifest distinguishes `download_verified` from the delivered
`verified` result. `output_root` points to the accessible delivered directory;
`service_output_root` identifies the durable working copy. Removing a record keeps
both copies. Exact-file erasure previews include both locations and still require
the existing native approval. An older isolated development fixture without a
registered delivery root retains the explicit `service_store` result.

The browser uses the full viewport, anchors its footer at the bottom and allocates
remaining space to the transfer list. The selected detail pane has a configurable
share; obsolete fixed grid heights are migrated while columns and sorting remain.

Repeat the filesystem checks with `python tests/integration/test_delivery.py` and
the real tracker/peer suite with `tests/integration/jobs_swarm.py` from a verified
visible foreground console. These tests include Windows Downloads delivery,
restart recovery, account isolation, record retention and reviewed file erasure.

For an existing installation, an administrator runs
`packaging\windows\Update-Jobs.ps1` from a visible foreground PowerShell console.
Success prints the registered program directory, an update ID and the SHA-256 of
the installed Downloads worker. An operator can run the same script with
`-VerifyOnly` to compare the installed host and worker files with the published
payload without stopping a service or changing anything. This verifies program
files; delivery of a book still requires its account's saved manifest and readable
bytes under the Windows Downloads folder.

For an existing queue, run `tests/desktop/torrenter_workspace.py` from a visible
console with the installed Jobs executable, `--installed`, the edition's loopback
`--controller` URL, `--username` and `--verify-completed COUNT`. Headed Chrome
signs in, reads that account's manifests, and verifies the length and SHA-256 of
every file in those completed jobs against the operator's Windows Downloads folder.
This mode does not add jobs, change preferences or remove files.

* `src/Tlachihuani.Jobs/` registers each approved provider adapter in the host. Torrenter supervises a private libtorrent worker and a Kestrel child carrying the browser assets. Windows Job Objects bind the children to their owner. Web process exit leaves the engine running.
* `workers/torrent/` owns a single-writer SQLite WAL journal, inspections, durable receipts, per-owner engine sessions, checkpoints and verification. Moving files uses a journaled intent and a same-volume rename. Erasure replays only approved file identities. The host process and the web facade access the journal through the worker.
* The installation identity is in `%ProgramData%\XAIHT\Tlachihuani.Jobs\installation.json`. The protected `state` directory contains the journal and owned files. The native Windows operator has read access to their own output subtree. Agent profile outputs are isolated. The manifest exposes verified paths to the authorized profile.
* Both storage roots reside on the service volume. Admission caps each torrent at 50 GiB and 4,096 files, reserves outstanding selected bytes and leaves 64 MiB free. Up to two transfers per owner and four per host are active at once. Public and private torrents have different discovery policies. Seeding is opt-in, rate-capped and bounded by time or upload ratio.
* Metadata discovery has its own four slots. Additional magnets wait in a durable first-in, first-out queue. During `resolving_metadata`, `lookup_state` is either `queued` (no peer timer running) or `active` (up to 180 seconds to obtain metadata). The authenticated inspection activity shows known and connected peer counts while active. An expired lookup can be retried with a new inspection. The separate limit of 32 retained inspections per account still applies.
* The worker package carries hash-verified CPython 3.12.10 and libtorrent 2.1.1. The release uses the private runtime under `Jobs\runtime`. Building and testing it does not install Python packages into Tlamatini.

## Repeat the checks

Use `.\scripts\Test-Jobs.ps1` after publishing to check transfers from a private seed, magnet resolution and independent content verification. To exercise the installed service in headed Chrome, supply `-Installed -BrowserPython <path> -Username <test-account> -Controller http://127.0.0.1:8000`. The test signs in to Tlamatini, reloads its workspace, submits a unique fixture and removes its record. Keep the foreground development console open for inspection.

The 31 October installed checks covered virtual-account service startup, delegated SCM stop/start, persisted provider stop, native identity verification, XT code approval and the browser admission/stop/remove workflow. Isolated checks also covered file and magnet admission, real 524,288-byte peer transfers with independently matched SHA-256, record removal with the bytes retained, authenticated SSE, hash publication, abrupt host recovery, cross-owner isolation, assertion replay, source path rejection, root relocation and explicit file-erasure approval. Full power-cycle, sign-out, Explorer restart, multi-day transfers, release signing and production packaging remain separate acceptance work.
