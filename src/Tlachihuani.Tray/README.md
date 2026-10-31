# XT tray companion

Right-click the original XT icon for **Show panel** or **Exit tray (service keeps running)**. Double-click and `--show` also open the native panel, which retains its Refresh, Start, Stop and Restart controls. Close hides the panel. Polling and native calls do not block the UI message pump.

[TrayMenu.cs](TrayMenu.cs) owns the menu and the opt-in switches for the six former rows. See [the tray contract](../../docs/panel-and-tray.md#tray) for reactivation and [packaging](../../packaging/windows/README.md) for the optional loopback link format. Force-stop and consent IPC are not implemented.
