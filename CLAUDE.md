# Vox AI Input - Claude Notes

`AGENTS.md` is the source of truth for this repository. Read it first, then use
these notes only as a short compatibility bridge for Claude-style agents.

## Current Project Facts

- Windows-first Python voice input app.
- Use Python 3.12 for local development and verification.
- Speech-to-text is local-first through sherpa-onnx models.
- Online transcription is not part of the main product path.
- Optional LLM polishing supports OpenAI Chat Completions, OpenAI Responses,
  Anthropic Messages, Azure OpenAI, and OpenAI-compatible gateways.
- Recommended polishing model: `gpt-5.4-mini`; quality-first option: `gpt-5.5`.
- Floating mic, result preview, tray icon, and hotkey flow share one recording
  state model.

## Before Work

1. Run `git status --short --branch`.
2. If the tree is clean and tracks a remote branch, run:

```powershell
git fetch --all --tags --prune
git pull --rebase
```

3. Read `AGENTS.md`, `progress.md`, `findings.md`, `task_plan.md`, and the
   latest `_release_note_v*.md`.
4. If `.venv` is missing, run `.\scripts\bootstrap_dev.ps1 -SkipVerify`.
5. If `config.yaml` is missing, copy `config.example.yaml` and keep it local.

## Guardrails

- Do not edit or commit `config.yaml`, `data/`, `models/`, eval outputs, caches,
  API keys, tokens, or private endpoints.
- Keep `host_header` optional for private gateway routing; `allow_insecure_tls`
  is the simple compatibility switch for trusted IP/self-signed endpoints.
- Do not introduce a separate CA bundle or certificate-management workflow
  unless the user explicitly asks for it.
- Use `apply_patch` for manual file edits.
- Prefer focused tests first, then the full suite before release or broad cleanup.
