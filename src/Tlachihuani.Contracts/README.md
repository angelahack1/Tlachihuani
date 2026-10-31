# Local protocol contracts

Closed request types, bounded framing, snake-case JSON and typed query/lifecycle envelopes. Protocol major is 1. The client acknowledges a complete reply with byte `0x06` before the service disconnects/reuses the pipe. Consult [implementation status](../../docs/implementation-status.md) for differences from the broader proposed protocol.
