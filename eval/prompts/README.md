# Prompt Evaluation Notes

- `default`: loaded from `src.polisher.POLISH_SYSTEM_PROMPT`.
- `baseline_old.txt`: the earlier minimal polishing prompt, kept for A/B tests.

Use `scripts/eval_polish.py --prompt-file eval/prompts/baseline_old.txt --prompt-name baseline_old`
to compare the old prompt against the current default prompt.
