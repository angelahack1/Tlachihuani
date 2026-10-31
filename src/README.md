# Source components

`Tlachihuani.slnx` builds seven production projects plus the executable verification suite. Service, Control and Tray are independent executable entry points. Contracts/Core do not reference Windows GUI code; Client and Windows share the fixed-service control implementation. No project imports Tlamatini's Python, database, agents or assemblies.

`Tlachihuani.Elevated` remains a design placeholder. See [implementation status](../docs/implementation-status.md) before treating any planned feature as implemented.
