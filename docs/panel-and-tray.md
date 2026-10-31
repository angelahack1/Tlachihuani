# Tlachihuani panel and tray experience

The original XT native tray/status foundation is implemented; the complete menu/consent design and Tlamatini panel remain planned. See [current status](implementation-status.md).

The panel belongs inside Tlamatini under **Panels → Tlachihuani**. This document and [the static concept](design/panel-concept.html) describe a future dialog; they do not add a menu entry or control a real service.

## Visual direction

Use Tlamatini's existing gray/slate surfaces, teal accent, Nunito typography, thin bright borders, 8 px card radius, and restrained shadows. Actual source tokens: surface `#4a4f5c`, header/footer `#444853`, accent `#55bbaa`, primary text `#f0f1f7`, body `#c1c5d0`. The implementation references `--tlm-dlg-*` rather than copying a second theme. Keep `dialog_theme.css` last.

Give the original XT icon a compact title position beside **Tlachihuani**, with a subtitle **Windows service · this Tlamatini host**. Use a status badge with icon/text, never color alone. Avoid a giant logo, decorative gauges, or invented workload graphs. Normal body text is roughly .88–.95 rem; title 1–1.1 rem.

Proposed desktop bounds: `min(80vw, 1120px)` wide by at most `74dvh` high; smaller windows use up to 94vw/63dvh with internal body scrolling and a reachable footer. This follows the recent Usage dialog's compact visual scale, not a new global rule for every dialog.

## Content structure

1. **Header:** XT icon, name, host scope, status badge, X.
2. **Overview:** service state, health/freshness, uptime, version. Show an em dash plus explanation where no observation exists. No invented zero values.
3. **Session strip:** tray status for this Windows session, distinguished from service status. A remote browser must not imply the tray belongs to its own computer.
4. **Activity:** bounded timestamped lifecycle events with plain language and expandable diagnostics. Monospace only for paths, IDs and error codes. No credentials or full environment dumps.
5. **Footer:** last observed timestamp, Refresh, Start, Stop; Restart as a secondary action; **Force kill…** separated as a danger action. A visible Close remains available during operations.

| Observed state | Controls and copy |
|---|---|
| Not installed | Refresh and installation guidance; no fake Start success or automatic installation |
| Stopped | Start enabled; Stop/Force kill disabled; explain delayed automatic start on next boot |
| Starting | Progress text and freshness; conflicting mutations disabled; Refresh/Close available |
| Running / healthy | Stop and Restart enabled; normal read-only monitoring |
| Running / health unavailable | State stays Running; show IPC error and last observation; do not guess a crash |
| Stop timed out | Explain timeout; Refresh, Retry Stop, Force kill… |
| Access denied | Explain required operator access; no elevated browser or hidden privilege retry |
| Connection lost | Explicit stale data; retry refresh; do not display old state as live |
| Incompatible protocol | Show detected versions and compatible-upgrade guidance; disable mutations |

## Interaction contract

Keep this Panels entry usable while chat is answering. Opening it starts a fresh status read; one poll is in flight at a time, coalesced by the server. Closing or hiding the document cancels UI fetches and stops its poll timer. It does not cancel an accepted service action. Reopening reconciles the last operation with SCM status.

Use the existing modal dismissal mechanism (`tlmDismiss` for a custom overlay). Escape, X and Close dismiss without executing anything. An outside click never dismisses. Trap keyboard focus; restore it to the opener when closing. Announce state changes through a polite live region, not every unchanged poll. Respect reduced motion, zoom and forced colors. Keep focus stable while data refreshes.

Stop uses a themed confirmation if an eventual workload reports active work. Force kill always has a themed confirmation: **Force stop Tlachihuani? Active work may be interrupted.** Cancel receives initial focus. A second host-side Windows elevation consent may be required; denying it is a clear canceled result. Browser-side confirmation does not replace host authorization.

## Tray

The icon is the original XT asset in [assets/branding](../assets/branding/README.md). Tooltip: **Tlachihuani — Running**, **Stopped**, or **Health unavailable**. Keep status text available for accessibility and high-contrast use; overlays must not obscure the XT mark.

The current XT context menu contains **Show panel** and **Exit tray (service keeps running)**. Show panel, double-click and `--show` open the same native window. That window still has Refresh, Start, Stop and Restart; the three-second status poll still updates it and the icon tooltip.

The six former menu entries are opt-in in [TrayMenu.cs](../src/Tlachihuani.Tray/TrayMenu.cs). Add the desired `Extra` flags to `Shown` and rebuild to restore them individually. The Tlamatini link reads the validated loopback URL only when selected; the state row displays an observation such as “Stopped”; the other four invoke the existing controller operations. See the adjacent code comments before changing or retiring a shortcut: its panel or CLI counterpart is independent. Force kill and local logs were design proposals, not implemented menu commands.

Exit tray states that the service keeps running. After logon, the companion shows whether the service is stopped or available; it does not implicitly start it. Re-register after Explorer restarts and maintain one icon per session. Windows controls whether that icon appears in the main notification row or its overflow; no silent pinning/settings changes.
