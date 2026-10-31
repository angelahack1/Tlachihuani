# Local control protocol v1 — proposed

The implemented synchronous subset and the required reply receipt byte are documented in [implementation status](implementation-status.md). Force-stop, consent IPC and persistent operation receipts below are future work.

The browser API, transient controller CLI and service IPC have separate responsibilities. The protocol is local-only; no TCP listener or new inbound firewall rule is planned.

## SCM and pipe roles

`Tlachihuani.Control` queries SCM to discover installation/state/PID even while the service is stopped or its IPC is broken. Start, Stop, and Restart use SCM. Health and bounded event history use the service's named pipe, proposed `\\.\pipe\XAIHT.Tlachihuani.v1.<installation-id>`. The installation ID is generated once by the installer, not supplied by a browser.

Use an explicit ACL and reject remote pipe clients. A single pipe can serve authorized local sessions; authenticate the connected Windows identity on every connection and authorize each operation. Do not trust a JSON `user`, `role`, or `pid` claim. Verify the pipe server identity against the live SCM service before trusting responses. Do not let a pipe-squatting process impersonate a stopped service.

Proposed framing: 4-byte little-endian byte length followed by one UTF-8 JSON object, maximum 64 KiB, one request and reply per exchange, a 3 s read deadline for status, and bounded concurrent clients (initial limit 16). Reject malformed UTF-8, unknown action, oversized body, wrong major version and trailing frames. No deserialization into arbitrary runtime types. Event reads use a cursor and at most 100 redacted entries.

## Closed operation set

| Surface | Allowed operations |
|---|---|
| Controller CLI | `status`, `start`, `stop`, `restart`, `events`, `operation-status`, `request-force-stop` |
| Service pipe | `hello`, `status`, `events`; later workload methods require separate design |
| Elevated helper | Fixed `Tlachihuani` service force-stop; no browser-selected PID, service, binary or shell |

Start/Stop must not depend on a responsive pipe. Force-stop must work against an unresponsive service; the elevated helper independently queries SCM and process identity. The GUI's force-stop request is an operation request routed to host consent, not an instruction to terminate a JSON PID.

For that consent handoff, the tray exposes a separate session pipe, proposed `\\.\pipe\XAIHT.Tlachihuani.Tray.v1.<session-id>`, with the interactive logon SID on its DACL and remote clients rejected. The controller locates the tray matching its authorized host Windows user/session, verifies its process identity, and submits a bounded pending request. The tray asks the person at that host to approve before starting UAC. This route does not pass through the hung service. If no matching tray exists, return the host-consent requirement; do not pick another user's session or launch elevation invisibly.

## Envelope

Examples are illustrative protocol fixtures, not observations or runtime configuration:

```json
{
  "protocol_major": 1,
  "protocol_minor": 0,
  "request_id": "00000000-0000-4000-8000-000000000001",
  "operation": "status"
}
```

```json
{
  "protocol_major": 1,
  "protocol_minor": 0,
  "request_id": "00000000-0000-4000-8000-000000000001",
  "ok": true,
  "error": null,
  "service": {
    "name": "Tlachihuani",
    "scm_state": "stopped",
    "health": "unknown",
    "instance_id": null,
    "pid": null,
    "version": null,
    "uptime_seconds": null,
    "last_heartbeat_utc": null
  }
}
```

Real replies also contain `observed_at_utc`, `installation_id`, capabilities and their reasons, and observation source. A service boot creates a fresh `instance_id`; PID is diagnostic data, never authority. Operation replies include `operation_id` and `phase` (`accepted`, `pending_host_consent`, `running`, `succeeded`, `failed`, `canceled`, or `timed_out`). A terminal success requires observed final state. Accepted is not succeeded.

Compatibility: reject an unknown major version. Minor versions may add optional fields; ignore unknown response fields but reject unknown commands. Both peers enforce framing and required-field bounds. Invalid JSON or empty stdout is failure even if the process exit code is zero.

## Errors and mapping

| Machine code | Meaning / suggested web status |
|---|---|
| `not_installed` | Valid status observation; action returns 409 |
| `access_denied` | Caller lacks app or Windows rights; 403 |
| `invalid_request` | Bad action/body or reused key with different action; 400/409 |
| `busy` | Conflicting lifecycle action is pending; 409 |
| `timeout` | Deadline expired; preserve last measured state; 504 |
| `unavailable` | Controller/pipe cannot be contacted; 503 |
| `incompatible_protocol` | Peer version cannot be used; 409 |
| `identity_changed` | Service instance changed since confirmation; no termination; 409 |
| `host_consent_required` | Local interactive consent still needed; accepted operation, not success |
| `canceled` | User dismissed confirmation/elevation; terminal canceled operation |
| `internal_error` | Redacted diagnostic ID plus actionable message; 500 |

Proposed CLI exit codes: 0 valid completed query/action, 2 invalid input, 3 not installed, 4 access denied, 5 conflict/identity change, 6 timeout, 7 incompatible protocol, 8 unavailable/internal failure. An accepted asynchronous operation returns 0 with its nonterminal phase; callers must inspect that phase. Structured stdout has exactly one bounded JSON reply; diagnostics go to stderr. Never infer success from exit code alone.

## Serialization and audit

Use a machine-scoped named mutex with a restricted DACL to serialize mutations across controller/tray instances. On abandoned ownership, query SCM and reconcile receipts before accepting another mutation. Read-only status remains independently callable. Store bounded operation receipts in Tlachihuani's own protected data area with atomic replacement; retention proposed 24 hours/1,000 operations.

Tlamatini audits its authenticated account plus operation ID in its main logger. The Windows layer audits the authenticated Windows SID and operation ID. These identities are different; the shared Windows account of Django does not automatically authorize every web user.
