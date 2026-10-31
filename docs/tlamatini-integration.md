# Future Tlamatini integration — explicitly deferred

Reference checkout: `C:\Development\XAIHT\Tlamatini`; upstream: [XAIHT/Tlamatini](https://github.com/XAIHT/Tlamatini). Every path below is relative to that checkout unless labeled proposed. **No file in that checkout should be changed during this scaffold or the first standalone implementation phase.**

## Observed integration points

| Existing source | Observed contract / future use |
|---|---|
| `Tlamatini/agent/templates/agent/agent_page.html:103` | `panels-menu-button`; Agentic Control Panel, Prompt Flow Panel, staff-only Admin. Add a future Tlachihuani item here, opening a dialog in the same page. |
| `Tlamatini/agent/static/agent/css/dialog_theme.css:49` | Shared `--tlm-dlg-*` tokens; this stylesheet stays last in the page cascade. |
| `Tlamatini/agent/static/agent/js/dialog_policy.js:50` | Viewport fitting and dismissal policy. Escape means the same as X/Cancel; outside click does not dismiss. |
| `Tlamatini/agent/static/agent/js/agent_page_ui.js:333` | Panels stay accessible during long chat operations. Preserve this; avoid a second menu-lock system. |
| `Tlamatini/agent/static/agent/js/agent_page_ui.js:385` | `restoreMenuControlsAfterOperation()` is the single menu restoration path. |
| `Tlamatini/agent/templates/agent/usage_dialog.html` | Existing self-contained modal structure with title, tabs, status, scroll body, reachable footer. |
| `Tlamatini/agent/static/agent/js/usage_dashboard.js` | Focus trap/return, `tlmDismiss`, abortable refresh, account-change handling. Reuse patterns, not its billing logic. |
| `Tlamatini/agent/urls.py:19` | `secure_get` is login-only; `secure_post` adds POST and CSRF. New views must also enforce allowed methods and service-control permissions. |
| `Tlamatini/agent/usage_views.py` | Small separate authenticated read-only view module; precedent for keeping service integration out of the large views file. |
| `Tlamatini/agent/windows_app_registration.py`, `agent_manifest.py` | Existing Tlamatini HKCU discovery. Read its documented values only; do not repurpose them as Tlachihuani ownership. |
| `Tlamatini/agent/apps.py`, `orphan_reaper.py`, root `uninstall_processes.py` | Existing pool/process cleanup; keep independently installed Tlachihuani outside its ownership. |
| `build.py`, `build_runtime_assets.py`, `copy_source_assets.py`, `apply_update.ps1` | Future adapter/static assets need source/frozen/update carriage checks. Tlachihuani binaries remain in their own release/install. |
| `Tlamatini/tlamatini/settings.py` | Future frontend change needs the existing STATIC_VERSION mechanism; do not replace its derived expression. |

## Proposed additions, not existing files

- `Tlamatini/agent/tlachihuani_views.py`: HTTP permission/method checks and response mapping.
- `Tlamatini/agent/services/tlachihuani_client.py`: installation discovery, fixed executable/argv, bounded subprocess JSON, timeout and protocol validation.
- `Tlamatini/agent/templates/agent/tlachihuani_dialog.html`.
- `Tlamatini/agent/static/agent/js/tlachihuani_panel.js`, exporting only `window.TlmTlachihuaniPanel`.
- `Tlamatini/agent/static/agent/css/tlachihuani_panel.css`, using shared tokens and scoped selectors.
- Focused backend tests and a visible browser harness for these exact paths.

## Proposed web API

`GET /agent/tlachihuani/status/` returns bounded basic status to authenticated users. `GET /agent/tlachihuani/events/` returns redacted diagnostics to staff. `POST /agent/tlachihuani/actions/` accepts only `start`, `stop`, `restart`, or `request_force_stop`, plus an idempotency ID. `GET /agent/tlachihuani/operations/<uuid>/` observes an accepted operation.

Staff-only mutations and Windows operator rights are both required; a disabled button is not authorization. GET never mutates. All POSTs are CSRF-protected. Include the current Tlamatini account ID in responses; discard late responses after account switches. Return `Cache-Control: no-store`.

The controller path comes from a validated Tlachihuani installation record, not browser JSON, PATH search, arbitrary registry strings, or the development checkout. The adapter uses an argument array and never a shell. It validates executable location/ownership, protocol version, bounded stdout and exit status. No browser supplies a PID, service name, filesystem target, or command.

Missing controller/service must not prevent Tlamatini startup or chat. Show **Not installed** with installation guidance. Discovery occurs on panel demand, outside `AppConfig.ready()`. Source mode may use an explicit developer-only override to this new project's built controller; frozen mode must not contain Angela's development path.

## Host/session discovery

Tlachihuani's installer will own a separate machine installation key, proposed `HKLM\Software\XAIHT\Tlachihuani`, with installation ID, binary paths, version and protocol major. Validate against SCM binary registration and administrator-owned files before execution. Read both registry views deliberately where required; no registry writes occur in this design.

For **Open in Tlamatini**, the tray keeps a validated per-user Tlamatini base URL and reads documented HKCU discovery as a hint. Existing `HKCU\Software\XAIHT\Tlamatini` describes install/catalog paths, not a guaranteed live server or web port. Never assume port 8000. Open the configured origin and planned `#tlachihuani` route after login; do not embed authentication tokens or silently launch a privileged server. Until panel integration ships, open the normal Tlamatini page and explain that the panel requires a compatible version.

## Deferred work boundary

No DB migration, MCP, ACP canvas node, wrapped LLM tool, skill registration, Compact gate, or prompt catalog entry is needed for this panel. If Angela later asks for model-driven service tools, separately register those in `tools.tool_gate_table()` and apply the full tool/permission/Exec Report contracts. Do not infer that feature from this request.
