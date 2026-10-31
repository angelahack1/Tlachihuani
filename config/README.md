# Configuration design

Future validated non-secret defaults and schema belong here. Runtime machine configuration belongs in the owned ProgramData directory; tray preferences in LocalAppData. Developer overrides remain ignored. No active runtime configuration exists yet.

Keep service identity fixed, bound every timeout/size, and never accept an executable/PID/shell command from a configuration field intended for status or lifecycle control.
