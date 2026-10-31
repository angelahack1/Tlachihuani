# Operating Torrenter

Torrenter downloads selected files in the independent Windows service `Tlachihuani.Jobs`. The XT tray, browser and original `Tlachihuani` service have separate lifetimes. Closing a window releases its UI session. Windows owns the download host under `NT SERVICE\Tlachihuani.Jobs`.

## Open the workspace

1. Right-click the **XT** icon and choose **Show panel → Services…**. The Services window shows Jobs, engine and web readiness, the active transfer count and the number of job records.
2. Choose **Open workspace**, then **Request pairing code**. Type the eight digits into **Services → Approve code**. Leave **Account** blank for your Windows profile. Enter the enrolled application account to share that account’s job IDs with an API client.
3. Choose **Add torrent**, upload a `.torrent` or enter a magnet, then **Inspect metadata**. Choose files, priorities, destination, resume and seeding policy. **Download selected files** creates the durable job.
4. Filter by tracker, category, tag, observed state or activity. **Preferences** saves the column order, widths, sorting and grid height for the paired account in this browser. Use the transfer’s **Verified output** tab to see its output directory and per-file SHA-256. **Stop** retains partial files until you choose **Start**. **Pause** pairs with **Resume**. **Cancel** ends the transfer permanently. **Remove record** retains files. **Erase files…** requires a separate exact-file review and approval in XT.

**Restart web** restarts the HTTP process independently of active peers. **Stop provider** drains Torrenter and persists the stop across Jobs restarts. **Stop Jobs** stops the entire provider host. Use **Start Jobs** and, if explicitly stopped, **Start provider** to bring it back.

Open the [workspace](http://127.0.0.1:12064/) or [API discovery](http://127.0.0.1:12064/api/v1). This deployment binds the dashboard to IPv4 loopback. Torrent traffic uses a separate peer socket.

## Windows installation

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
'{"op":"catalog"}' | & (Join-Path $base 'Jobs\Tlachihuani.Jobs.exe') --control
Invoke-RestMethod 'http://127.0.0.1:12064/api/v1/health'
```

To enable XT on future logins, run `.\packaging\windows\Set-TrayStartup.ps1` as the intended Windows user. Jobs has its own delayed automatic startup and SCM recovery policy.

## REST contract for the browser and wrapped agent

Use the API prefix `/api/v1`. For automation, select **Issue API credential** in XT or enroll a trusted gateway through the native pipe. Scopes are `read`, `submit`, `control`, `remove` and `erase`. Send credentials as `Authorization: Bearer <token>`. Job IDs and receipts belong to the issuing account. Direct tokens expire after one hour, paired browser tokens after 30 minutes and gateway-issued tokens after five minutes.

| Intent | Request | Result |
|---|---|---|
| Discover | GET `/`, `/health`, authenticated `/capabilities` | Protocol, engine readiness, scopes, approved roots and verbs |
| Inspect | POST `/inspections` with multipart field `file` or JSON `{"magnet":"magnet:…"}`. GET `/inspections/{id}` | Review stable file IDs and sizes. Magnet metadata can take time |
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

* `src/Tlachihuani.Jobs/` registers each approved provider adapter in the host. Torrenter supervises a private libtorrent worker and a Kestrel child carrying the browser assets. Windows Job Objects bind the children to their owner. Web process exit leaves the engine running.
* `workers/torrent/` owns a single-writer SQLite WAL journal, inspections, durable receipts, per-owner engine sessions, checkpoints and verification. Moving files uses a journaled intent and a same-volume rename. Erasure replays only approved file identities. The host process and the web facade access the journal through the worker.
* The installation identity is in `%ProgramData%\XAIHT\Tlachihuani.Jobs\installation.json`. The protected `state` directory contains the journal and owned files. The native Windows operator has read access to their own output subtree. Agent profile outputs are isolated. The manifest exposes verified paths to the authorized profile.
* Both storage roots reside on the service volume. Admission caps each torrent at 50 GiB and 4,096 files, reserves outstanding selected bytes and leaves 64 MiB free. Up to two transfers per owner and four per host are active at once. Public and private torrents have different discovery policies. Seeding is opt-in, rate-capped and bounded by time or upload ratio.
* The worker package carries hash-verified CPython 3.12.10 and libtorrent 2.1.1. The release uses the private runtime under `Jobs\runtime`. Building and testing it does not install Python packages into Tlamatini.

## Repeat the checks

Use `.\scripts\Test-Jobs.ps1` after publishing for a private tracker, seed, isolated Jobs host and independent content verification. Supply `-BrowserPython <path-to-python.exe>` for the headed Chrome exercise with Playwright. For installed browser acceptance, use `-Installed -BrowserPython <path>`; add `-TrayProcessId <installed-XT-PID>` to exercise the real native approval dialog with pywin32. The installed browser test uses a small unique, private fixture and removes its job record. Keep the visible foreground development console open for inspection.

The 31 October installed checks covered virtual-account service startup, delegated SCM stop/start, persisted provider stop, native identity verification, XT code approval and the browser admission/stop/remove workflow. Isolated checks also covered file and magnet admission, real 524,288-byte peer transfers with independently matched SHA-256, record removal with the bytes retained, authenticated SSE, hash publication, abrupt host recovery, cross-owner isolation, assertion replay, source path rejection, root relocation and explicit file-erasure approval. Full power-cycle, sign-out, Explorer restart, multi-day transfers, release signing and production packaging remain separate acceptance work.
