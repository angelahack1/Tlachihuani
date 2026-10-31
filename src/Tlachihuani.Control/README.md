# JSON controller

Supported: `status`, `events [--cursor N]`, `start`, `stop`, `restart`. Exactly one JSON reply goes to stdout. Exit codes: 0 completed, 2 invalid input, 3 absent installation, 4 denied, 5 conflict/identity changed, 6 timeout, 7 incompatible protocol, 8 other failure. No caller-selected service, executable, PID, shell or elevation is accepted. Force-stop and persistent operation receipts remain planned.
