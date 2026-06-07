# AI-Assisted Development Governance

This document defines how AI-assisted tools are used for MemoryX project maintenance.
AI tools are not integrated into the MemoryX runtime.

## Approved Use Cases

- Pull request review (Python source, tests, CI)
- Issue triage (classification, label suggestions)
- Test generation (contract tests)
- Release validation (pre-release audit)
- Documentation alignment

## Boundaries

- No runtime integration: AI tools never called from MemoryX runtime
- No default model: MemoryX does not ship with any AI provider
- No API key storage: keys in environment variables only
- Human-in-the-loop: all outputs are advisory
- No silent execution: all workflows explicitly triggered
