# Privileges, installation and ownership

Implementation update: [current status](implementation-status.md) and [packaging scripts](../packaging/windows/README.md) describe the first foundation. The broader requirements below are not all verified yet.

Design only. This preparation performs no registry, startup, SCM, ACL, firewall, security-setting or installed-application changes.

## Identities

Run the service with a dedicated least-privilege virtual service account, proposed `NT SERVICE\Tlachihuani`, and an own-process SCM registration. Grant only required access to its own data/log directories. No LocalSystem or administrator token is justified by the initial heartbeat/status workload. Reassess if Angela defines a workload that needs additional resources.

The interactive tray runs unelevated as the signed-in user. Proposed local group **Tlachihuani Operators** receives query/start/stop rights on this service, with status-only access for explicitly selected viewers. The installer must distinguish the initiating user from an elevation account and not silently grant all authenticated users lifecycle privileges. Do not alter Tlamatini's existing rights.

Named-pipe DACLs explicitly allow the service identity, administrators and configured operators/viewers with operation-specific enforcement. Reject network clients; the default pipe DACL is insufficient. Use precise rights that do not accidentally grant pipe-instance creation to clients. See [Microsoft's named-pipe security reference](https://learn.microsoft.com/en-us/windows/win32/ipc/named-pipe-security-and-access-rights).

## Force termination

Normal controls remain unelevated when the operator has SCM rights. Force termination uses a short-lived, narrowly scoped administrator helper only after explicit host-side consent. The planned Tlamatini panel initiates the request and reports its outcome; a compatible host tray handles local consent/UAC. With no eligible interactive tray/session, return `host_consent_required` with guidance instead of attempting invisible elevation. Remote browsers cannot approve a Windows elevation dialog on somebody else's desktop.

The helper accepts only a request ID/nonce through an ACL-protected, short-lived result channel. It independently resolves the fixed SCM service, verifies own-process type, installation-owned binary path, PID creation time, and expected instance captured for the confirmation. Open the process handle, recheck identity before termination, and wait for that exact handle to signal exit. PID reuse or identity mismatch cancels the operation. Windows SCM state must subsequently be STOPPED. No process-name sweep; no termination of unrelated agents, browsers, consoles, or Explorer.

The first release disables SCM failure restart actions, so Force kill stays stopped for the current boot. Do not temporarily rewrite recovery policy in an ad hoc helper. If graceful shutdown already completed, return a truthful already-stopped result. If it restarted into a new instance, require fresh observation/confirmation.

## Installation and upgrade design

The future installer requires explicit administration for the machine service and Program Files. It validates destination ownership and reparse points, writes its own binary/installation manifest, creates data-directory ACLs and Event Log source, configures the service and failure policy, and optionally enables the tray at logon for selected users. No installation runs from this scaffold.

Installation metadata lives in the new project's own registry key and signed/hashed manifest; it must agree with SCM. The trusted controller path must not be replaceable by a normal user. Registry values alone do not authorize execution.

Upgrade: authenticate the delivered package, acquire the installation operation lock, record owned configuration/state, stop gracefully, replace binaries transactionally, verify version/protocol compatibility, and restart only if the recorded desired state requires it. A failure restores the prior usable binaries and reports the real outcome. Test power-loss/locked-file boundaries before promising rollback. Signing certificate/package distribution choices are future release decisions, not established credentials.

Uninstall: request confirmation in the future uninstaller, stop only this service and its owned tray instances, remove only its own SCM/startup/discovery registrations and binaries, and separately ask whether to retain its logs/configuration. Never touch Tlamatini, its database, `agents/`, `Templates/`, file associations, or Windows UserChoice keys.

## Storage and diagnostics

Proposed log retention: 5 files × 10 MiB, plus bounded Windows Event Log startup/fatal/lifecycle entries. Limit event payload lengths and escape text before browser rendering. Keep installation paths and detailed errors behind staff/operator views. Never store Tlamatini passwords, browser cookies, API keys, chat messages, or full inherited environment blocks.

No network control endpoint, firewall opening, remote shell, automatic updater, credential store, or scheduled worker is part of the initial design. Add a capability only after its actual workload and permission needs are specified.
