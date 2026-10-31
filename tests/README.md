# Verification

`Tlachihuani.Checks` is a dependency-free executable suite invoked by the visible `scripts/Build.ps1 -Mode Check`. It covers framing attacks, protocol bounds, event retention, lifecycle idempotence/order/timeouts, startup races, native local IPC, server-image rejection, 32 concurrent real-host clients, heartbeat, correlated version refusal and graceful console shutdown.

The older unit/contracts/desktop/integration directories reserve broader acceptance categories. See [dated results](../docs/verification/2026-10-11-foundation.md) for actual coverage. SCM registration, cross-account security and shell tray behavior require separate installed acceptance.
