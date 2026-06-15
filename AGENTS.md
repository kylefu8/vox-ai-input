# AGENTS.md

## Project Snapshot

Vox AI Input is a Windows-first Python voice input app.

Core flow:

1. Record audio through a global hotkey or the floating mic control.
2. Transcribe locally with sherpa-onnx models.
3. Optionally polish, translate, or produce bilingual output through an LLM provider.
4. Paste the final text into the active app and save history metadata.

The product is local-STT-first. Do not reintroduce online transcription unless the user explicitly asks for that direction.

## Current Product Direction

- Local transcription is the core path.
- AI polishing is optional and should support OpenAI Chat Completions, OpenAI Responses, Anthropic Messages, and OpenAI-compatible gateways.
- The recommended polish model is `gpt-5.4-mini` for the default balanced path; `gpt-5.5` is the quality-first option.
- Settings should stay focused and approachable. Avoid exposing engineering-only knobs unless there is a clear user-facing reason.
- The UI should feel like a compact Windows utility: clear, efficient, restrained, and responsive.
- The floating mic, tray icon, preview overlays, and hotkey path must share one recording state model.

## Repository Layout

- `run.py` - main entry point and CLI flags.
- `src/app.py` - application controller and recording state orchestration.
- `src/voice_pipeline.py` - transcribe -> polish -> output workflow.
- `src/local_transcriber.py` / `src/model_manager.py` - local STT model logic.
- `src/polisher.py` - default prompt, polish, translation, fallback handling.
- `src/llm_clients.py` - LLM provider adapters and model discovery.
- `src/settings_window.py` - settings UI.
- `src/floating_control.py` - draggable on-screen recording button.
- `src/preview_overlay.py` - result preview capsule.
- `src/ui_theme.py` - shared semantic theme tokens.
- `src/tk_runtime.py` - process-level Tk root lifecycle guard.
- `src/i18n.py` - Chinese/English UI strings.
- `eval/` and `scripts/eval_polish.py` - local polish/translation evaluation harness.
- `task_plan.md`, `progress.md`, `findings.md` - project memory across Codex sessions.

## Local Setup

Use Python 3.12 on Windows.

### GitHub Sync Before Work

At the start of a new Codex task in an existing checkout:

1. Run `git status --short --branch` first.
2. If the working tree is clean and the current branch tracks a remote branch, run:

```powershell
git fetch --all --tags --prune
git pull --rebase
```

3. If there are uncommitted local changes, do not pull/rebase blindly. Summarize the changed files and ask whether to commit, stash, or keep working on the local changes.
4. After syncing, read `AGENTS.md`, `progress.md`, `findings.md`, `task_plan.md`, and the latest `_release_note_v*.md` before making product or architecture changes.
5. If pulled commits changed dependency files such as `requirements.txt` or `requirements-dev.txt`, rerun `.\scripts\bootstrap_dev.ps1 -SkipVerify`.
6. If pulled commits changed setup or test rules, follow the newest instructions in `AGENTS.md`.

### Fresh Clone Bootstrap

When starting work in a fresh clone or on a new machine, first check whether `.venv` and `config.yaml` exist.

- If `.venv` is missing, run `.\scripts\bootstrap_dev.ps1 -SkipVerify` before code exploration that depends on installed packages.
- If the user asks for a full setup or release verification, run `.\scripts\bootstrap_dev.ps1` so compile and tests run as part of setup.
- If `config.yaml` is missing but `.venv` already exists, copy `config.example.yaml` to `config.yaml` and remind the user to fill machine-local endpoint/API key/model settings.
- Do not edit or commit `config.yaml`.
- If Codex approval settings require confirmation before running scripts or installing dependencies, ask for approval and explain that this is the project bootstrap step.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt
Copy-Item config.example.yaml config.yaml
```

Shortcut:

```powershell
.\scripts\bootstrap_dev.ps1
```

Detailed bootstrap documentation: `docs/bootstrap-dev.md`.
Codex entry prompts for fresh clone and existing checkout workflows: `docs/codex-entry-prompts.md`.

## Verification

Before committing, run:

```powershell
py -3.12 -m compileall -q run.py src tests
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q
```

For focused work, run the smallest relevant tests first, then the full suite before release or broad refactors.

Useful focused groups:

```powershell
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q tests/test_llm_clients.py tests/test_polisher_prompt.py
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q tests/test_settings_window_profiles.py tests/test_i18n.py
uv run --python 3.12 --with-requirements requirements-dev.txt python -m pytest -q tests/test_voice_pipeline.py tests/test_integration.py
```

## Run Commands

```powershell
python run.py
python run.py --visible
python run.py --open-settings
python run.py --test
python run.py --version
```

## Do Not Commit

Never commit secrets, local runtime state, downloaded models, generated eval output, or caches:

- `config.yaml`
- `data/`
- `models/`
- `eval/results/`
- `eval/reports/`
- `__pycache__/`
- `.pytest_cache/`
- local API keys, tokens, or private endpoint credentials

## Engineering Rules

- Prefer existing project patterns over introducing new frameworks.
- Keep changes scoped to the user request.
- Use `rg` for code search.
- Use `apply_patch` for manual edits.
- Do not revert user changes unless explicitly asked.
- Be careful with Tkinter threading; bind `ImageTk.PhotoImage` to the active root/window.
- On Windows, preserve DPI awareness paths through `run.py`; avoid testing the GUI through ad-hoc `python -c` launches when visual clarity matters.
- If polishing fails and falls back to raw text, preserve visible fallback metadata so the user can tell connection failure from weak model behavior.
- Keep `endpoint` display value and resolved runtime `base_url` separate.

## UI Rules

- Prefer icon buttons for repeated tool actions and text buttons for global state changes such as Save, Cancel, Validate, and Record.
- Keep settings dense but legible. Avoid landing-page style layouts, oversized copy, nested cards, and decorative gradients.
- Text must not be clipped in English or Chinese.
- Theme changes should be in-place where possible; avoid destroying and rebuilding the whole settings window for color-only changes.
- Dialogs should be centered before they appear and must follow the active theme.

## Prompt And Evaluation Notes

- Default polishing should actively clean real speech artifacts: filler words, repeated fragments, obvious mixed Chinese-English transcription residue, and incomplete trailing fragments.
- Preserve uncertain names and internal abbreviations instead of guessing.
- Only summarize or restructure aggressively when the transcript explicitly asks for that, or when it clearly contains a list/steps/todos.
- For model comparisons, use `scripts/eval_polish.py` and keep generated reports out of git.

## Release Checklist

1. Update `run.py` and `installer.iss` version numbers.
2. Update `README.md` and `README_zh.md`.
3. Add `_release_note_vX.Y.Z.md`.
4. Update `progress.md` and, when useful, `findings.md` / `task_plan.md`.
5. Run compile and full tests.
6. Commit to `master`.
7. Push `master`.
8. Tag `vX.Y.Z` and push the tag to trigger GitHub Actions.
9. Confirm the GitHub Release has the installer, zip, update manifest, and config template.

## Multi-Machine Workflow

- Treat GitHub as the source of truth.
- Start each machine with `git pull --rebase`.
- Commit before switching machines.
- Use separate branches for parallel work.
- Avoid running two Codex sessions against the same branch and the same files at the same time.
- Keep project memory in `progress.md`, `findings.md`, and release notes so a fresh Codex session can continue without access to old chat history.
