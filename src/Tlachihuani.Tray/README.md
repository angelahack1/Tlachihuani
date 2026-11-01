# XT tray companion

Right-click XT and choose **Start Services** to bring both Windows services and the Torrenter REST API online. XT turns from gray to color when the API is ready. **Stop Services** shuts down the Jobs host, its provider processes and the primary service. The gray tray icon stays available to start them again. **Show panel** and double-click open the individual controls. The last entry closes only the tray. It reads **Exit tray** once both services are confirmed stopped or absent, and **Exit tray (service keeps running)** otherwise.

[TrayMenu.cs](TrayMenu.cs) owns the menu and the opt-in switches for the six former rows. See [the tray contract](../../docs/panel-and-tray.md#tray) for reactivation and [packaging](../../packaging/windows/README.md) for the optional loopback link format. Force-stop and consent IPC are not implemented.
