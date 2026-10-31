# Shared controller client

Combines authoritative SCM observations with a separate bounded pipe-health query. Verifies installation/path/PID and a held process identity before trusting replies. Start/Stop/Restart use SCM even if IPC is unavailable. Console development mode is read-only and always reports SCM as `not_applicable`.
