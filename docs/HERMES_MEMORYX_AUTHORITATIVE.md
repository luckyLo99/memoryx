# Hermes + MemoryX Authoritative Integration

This document records the verified way to use MemoryX as the active Hermes memory provider and to route Hermes native memory writes into MemoryX.

## Verified status

- Hermes provider: memoryx
- Hermes plugin status: installed and available
- Native memory write path: routed to MemoryX by authoritative patch
- Built-in MEMORY.md / USER.md: not used for MemoryX authoritative writes

## Provider installation

The MemoryX Hermes provider files live in two places:
- **Repository**: `integrations/hermes/memory_provider/memoryx/`
- **Hermes runtime**: `~/.hermes/hermes-agent/plugins/memory/memoryx/`

To install:

```bash
mkdir -p ~/.hermes/hermes-agent/plugins/memory/memoryx
rm -rf ~/.hermes/hermes-agent/plugins/memory/memoryx/*
cp -r integrations/hermes/memory_provider/memoryx/* ~/.hermes/hermes-agent/plugins/memory/memoryx/
```

## Why this integration exists

Hermes has a built-in memory system that may still report itself as always active.
MemoryX provider activation alone is not enough to guarantee that the native
Hermes `memory()` tool writes only to MemoryX.

This integration therefore has two separate parts:

1. A Hermes MemoryX provider.
2. An authoritative patch that routes native Hermes `memory()` writes into MemoryX.

The verified target behavior is:

- `hermes memory status` shows `Provider: memoryx`.
- The MemoryX provider is installed and available.
- Native Hermes `memory()` writes go to MemoryX.
- Native Hermes `memory()` writes do not create or update built-in `MEMORY.md` or `USER.md`.

## Repository layout

The Hermes MemoryX provider is stored in the repository here:

```text
integrations/hermes/memory_provider/memoryx/
```

The authoritative patch and verification scripts are stored here:

```text
integrations/hermes/scripts/patch_hermes_memory_tool.py
integrations/hermes/scripts/verify_hermes_memoryx_authoritative.py
```

Do not confuse the provider with the runtime plugin:

```text
integrations/hermes/plugins/memoryx_runtime/
```

The runtime plugin can handle lifecycle hooks, but it does not replace the
Hermes native `memory()` write path by itself.

## Install or refresh the Hermes MemoryX provider

The provider should be installed into the Hermes agent plugin directory:

```bash
cd "$HOME/src/memoryx"

mkdir -p "$HOME/.hermes/hermes-agent/plugins/memory"
rm -rf "$HOME/.hermes/hermes-agent/plugins/memory/memoryx"
cp -r integrations/hermes/memory_provider/memoryx \
  "$HOME/.hermes/hermes-agent/plugins/memory/memoryx"
```

## Install MemoryX into the Hermes virtual environment

Hermes runs inside its own virtual environment. Install the current MemoryX
checkout into that environment:

```bash
cd "$HOME/src/memoryx"

"$HOME/.hermes/hermes-agent/venv/bin/python" -m pip install -e "$PWD"
```

## Configure Hermes

Set MemoryX as the Hermes memory provider:

```bash
hermes config set memory.provider memoryx
```

The Hermes environment should include:

```text
MEMORYX_HOME=$HOME/.hermes/memoryx
MEMORYX_AUTHORITATIVE=1
MEMORYX_AUTO_SYNC_TURNS=1
```

For SiliconFlow embeddings, use placeholder values in documentation:

```text
MEMORYX_EMBEDDING_ENDPOINT=https://api.siliconflow.cn/v1/embeddings
MEMORYX_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-8B
MEMORYX_EMBEDDING_API_KEY=your_siliconflow_api_key
```

Never commit a real API key.

## Apply the authoritative patch

Apply the authoritative patch from the MemoryX repository:

```bash
cd "$HOME/src/memoryx"

python3 integrations/hermes/scripts/patch_hermes_memory_tool.py
```

After patching, confirm Hermes still sees MemoryX:

```bash
hermes memory status
```

Expected important lines:

```text
Provider:  memoryx
Plugin:    installed ✓
Status:    available ✓
memoryx  (no setup needed) ← active
```

Hermes may still display:

```text
Built-in:  always active
```

That is a Hermes status display behavior. The authoritative verification below
checks the actual native `memory()` write path.

## Verify authoritative MemoryX behavior

Run the verification script from the Hermes agent checkout:

```bash
cd "$HOME/.hermes/hermes-agent"

MEMORYX_AUTHORITATIVE=1 MEMORYX_HOME="$HOME/.hermes/memoryx" \
  "$HOME/.hermes/hermes-agent/venv/bin/python" \
  "$HOME/src/memoryx/integrations/hermes/scripts/verify_hermes_memoryx_authoritative.py"
```

Expected result:

```text
PASS: MemoryXProvider available
PASS: memory() returned provider=memoryx
PASS: memory() did not write MEMORY.md or USER.md
PASS: memory() wrote to MemoryX database
```

## After Hermes updates

A Hermes update may replace this file:

```text
~/.hermes/hermes-agent/tools/memory_tool.py
```

After updating Hermes, re-run:

```bash
cd "$HOME/src/memoryx"

python3 integrations/hermes/scripts/patch_hermes_memory_tool.py
hermes memory status
```

Then re-run the authoritative verification script.

## Verified test status

This integration was verified with:

```text
Hermes Agent v0.15.2
pytest: 331 passed, 1 skipped
SiliconFlow embedding dimension: 4096
Hermes authoritative verify: PASS
```
