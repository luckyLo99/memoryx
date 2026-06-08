# MemoryX Hermes Provider

This provider connects Hermes Agent to MemoryX.

Runtime data must stay local:
- ~/.hermes/.env
- ~/.hermes/memoryx/
- ~/.hermes/memories/
- *.db
- *.sqlite
- logs, cache, traces

Authoritative mode:
- MEMORYX_AUTHORITATIVE=1 routes Hermes memory() writes into MemoryX.
