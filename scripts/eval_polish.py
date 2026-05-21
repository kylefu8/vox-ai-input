"""
Run polishing/translation evaluations and generate a static HTML report.

Examples:
  python scripts/eval_polish.py --dry-run --limit 3
  python scripts/eval_polish.py --models gpt-4o-mini,gpt-5.4-mini --limit 5
  python scripts/eval_polish.py --api-type openai_responses --models gpt-5.4,gpt-5.5
  python scripts/eval_polish.py --prompt-file eval/prompts/baseline_old.txt --prompt-name baseline_old
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import ssl
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_llm_profile_config  # noqa: E402
from src.llm_clients import (  # noqa: E402
    LLMOptions,
    create_llm_client,
    validate_llm_profile_for_provider,
    _extract_openai_responses_text,
)
from src.polisher import build_prompt  # noqa: E402


DEFAULT_MODELS = [
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5.5",
    "gpt-4o",
    "gpt-4o-mini",
]

SCENARIOS = {
    "polish": {
        "label": "润色",
        "translate_to": "",
        "show_original": False,
        "target": "",
    },
    "translate_en": {
        "label": "润色 + 英译文",
        "translate_to": "en",
        "show_original": False,
        "target": "en",
    },
    "translate_en_original": {
        "label": "润色 + 英译文 + 原文",
        "translate_to": "en",
        "show_original": True,
        "target": "en",
    },
    "translate_zh": {
        "label": "润色 + 中译文",
        "translate_to": "zh",
        "show_original": False,
        "target": "zh",
    },
    "translate_zh_original": {
        "label": "润色 + 中译文 + 原文",
        "translate_to": "zh",
        "show_original": True,
        "target": "zh",
    },
}


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_cases(path: Path, case_ids: list[str] | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    data = load_yaml(path)
    cases = list(data.get("cases", []) or [])
    if case_ids:
        wanted = set(case_ids)
        cases = [case for case in cases if case.get("id") in wanted]
    if limit:
        cases = cases[:limit]
    return cases


def scenario_applies(case: dict[str, Any], scenario_id: str) -> bool:
    if scenario_id == "polish":
        return True
    target = SCENARIOS[scenario_id]["target"]
    return target in (case.get("translation_targets") or [])


def resolve_api_key(profile: dict[str, Any]) -> str:
    env_name = str(profile.get("api_key_env") or "").strip()
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    return str(profile.get("api_key") or "").strip()


def profile_for_model(
    base_profile: dict[str, Any],
    model: str,
    api_type: str,
    skip_validate: bool,
) -> tuple[dict[str, Any], str]:
    profile = dict(base_profile)
    profile["model"] = model
    if profile.get("deployment"):
        profile["deployment"] = model

    requested = api_type
    if requested == "profile":
        requested = str(profile.get("provider") or "auto").strip() or "auto"

    if requested != "auto":
        profile["provider"] = requested

    if skip_validate:
        return profile, "skipped"

    endpoint = str(profile.get("endpoint") or profile.get("base_url") or "").strip()
    api_key = resolve_api_key(profile)
    validated, response, _errors = validate_llm_profile_for_provider(
        requested,
        endpoint,
        api_key,
        model,
    )
    if profile.get("api_key_env"):
        validated["api_key_env"] = profile["api_key_env"]
        validated.pop("api_key", None)
    return validated, response


class DirectOpenAIHTTPClient:
    """Small evaluation-only client for endpoint/IP + Host header workarounds."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        host_header: str = "",
        tls_verify: bool = True,
        timeout: float = 60.0,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.host_header = host_header.strip()
        self.timeout = timeout
        self.context = None if tls_verify else ssl._create_unverified_context()

    def complete_text(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        if self.provider == "openai_responses":
            return self._complete_responses(system_prompt, user_prompt, options)
        return self._complete_chat(system_prompt, user_prompt, options)

    def _headers(self) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }
        if self.host_header:
            headers["host"] = self.host_header
        return headers

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib_request(
            f"{self.base_url}{path}",
            payload,
            self._headers(),
        )
        try:
            with urllib_urlopen(req, timeout=self.timeout, context=self.context) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(str(e)) from e

    def _complete_chat(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": options.max_tokens,
            "temperature": options.temperature,
        }
        data = self._post("/chat/completions", payload)
        try:
            return data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raise RuntimeError(f"Unexpected chat response: {str(data)[:500]}") from e

    def _complete_responses(self, system_prompt: str, user_prompt: str, options: LLMOptions) -> str:
        payload = {
            "model": self.model_name,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": options.max_tokens,
        }
        if options.temperature not in (None, 0, 0.0):
            payload["temperature"] = options.temperature
        return _extract_openai_responses_text(self._post("/responses", payload))


def urllib_request(url: str, payload: dict[str, Any], headers: dict[str, str]):
    import urllib.request

    return urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers=headers,
    )


def urllib_urlopen(req, timeout: float, context):
    import urllib.request

    return urllib.request.urlopen(req, timeout=timeout, context=context)


def direct_client_for_model(
    base_profile: dict[str, Any],
    model: str,
    api_type: str,
    host_header: str,
    tls_verify: bool,
    skip_validate: bool,
) -> tuple[DirectOpenAIHTTPClient, str, str]:
    endpoint = str(base_profile.get("base_url") or base_profile.get("endpoint") or "").strip()
    api_key = resolve_api_key(base_profile)
    requested = api_type
    if requested == "profile":
        requested = str(base_profile.get("provider") or "auto").strip() or "auto"

    providers = [requested]
    if requested == "auto":
        providers = ["openai_compatible", "openai_responses"]

    errors: list[str] = []
    for provider in providers:
        if provider not in ("openai_compatible", "openai_responses"):
            errors.append(f"{provider}: direct mode only supports OpenAI Chat/Responses.")
            continue
        client = DirectOpenAIHTTPClient(
            provider=provider,
            base_url=endpoint,
            api_key=api_key,
            model=model,
            host_header=host_header,
            tls_verify=tls_verify,
            timeout=60.0,
        )
        if skip_validate:
            return client, provider, "skipped"
        try:
            response = client.complete_text(
                "You are a connectivity check. Reply with OK only.",
                "Reply OK.",
                LLMOptions(max_tokens=64, temperature=0),
            ).strip()
            if not response:
                raise RuntimeError("empty response")
            return client, provider, response
        except Exception as e:
            errors.append(f"{provider}: {e}")

    raise RuntimeError("Direct endpoint validation failed.\n\n" + "\n".join(errors))


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:12]


def count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def count_latin_words(text: str) -> int:
    return len(re.findall(r"[A-Za-z]{2,}", text or ""))


def split_blocks(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text.strip()) if block.strip()]


def auto_checks(output: str, case: dict[str, Any], scenario_id: str, status: str) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = ""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    if status != "ok":
        add("request_ok", False, status)
        return {"checks": checks, "score": 0.0, "issues": [status]}

    text = (output or "").strip()
    scenario = SCENARIOS[scenario_id]
    target = scenario["target"]

    add("non_empty", bool(text), "output is empty" if not text else "")
    add("no_transcript_tag", "<speech_transcript>" not in text and "</speech_transcript>" not in text)
    chatty = [
        "作为AI",
        "作为 AI",
        "我无法",
        "I cannot",
        "I can't",
        "Here is",
        "Here's",
    ]
    add("not_chatty", not any(marker.lower() in text.lower() for marker in chatty))

    label_patterns = ["原文：", "翻译：", "Original:", "Translation:"]
    add("no_extra_labels", not any(label in text for label in label_patterns))

    terms = [str(term) for term in (case.get("preserve_terms") or []) if str(term).strip()]
    if terms:
        lowered = text.lower()
        missing = [term for term in terms if term.lower() not in lowered]
        add("preserve_terms", not missing, ", ".join(missing[:5]))

    if scenario["show_original"]:
        blocks = split_blocks(text)
        add("two_blocks", len(blocks) >= 2, f"block_count={len(blocks)}")
        language_text = blocks[-1] if blocks else text
    else:
        add("not_over_fragmented", len(split_blocks(text)) <= 6, "too many blank-line blocks")
        language_text = text

    if scenario_id == "polish":
        language = case.get("language")
        if language == "zh":
            add("keeps_chinese", count_cjk(language_text) > 0)
        elif language == "en":
            add("keeps_english", count_cjk(language_text) <= 2 and count_latin_words(language_text) >= 2)
    elif target == "en":
        cjk = count_cjk(language_text)
        add("mostly_english", cjk <= max(4, int(len(language_text) * 0.18)), f"cjk={cjk}")
    elif target == "zh":
        add("contains_chinese", count_cjk(language_text) >= 2)

    raw = str(case.get("text") or "")
    if len(raw) >= 20 and scenario_id == "polish":
        ratio = len(text) / max(1, len(raw))
        add("reasonable_length", 0.45 <= ratio <= 2.2, f"ratio={ratio:.2f}")

    ok_count = sum(1 for check in checks if check["ok"])
    score = ok_count / len(checks) if checks else 0.0
    issues = [
        f"{check['name']}: {check['detail']}".strip(": ")
        for check in checks
        if not check["ok"]
    ]
    return {"checks": checks, "score": round(score, 4), "issues": issues}


def dry_output(case: dict[str, Any], scenario_id: str) -> str:
    text = str(case.get("text") or "").strip()
    scenario = SCENARIOS[scenario_id]
    if scenario_id == "polish":
        return text
    if scenario["show_original"]:
        return f"{text}\n\n[DRY RUN translation to {scenario['target']}]"
    return f"[DRY RUN translation to {scenario['target']}] {text}"


def run_case(
    client: Any,
    model: str,
    api_type: str,
    prompt_name: str,
    base_prompt: str,
    case: dict[str, Any],
    scenario_id: str,
    dry_run: bool,
) -> dict[str, Any]:
    scenario = SCENARIOS[scenario_id]
    system_prompt = build_prompt(
        base_prompt,
        translate_to=scenario["translate_to"],
        show_original=scenario["show_original"],
    )
    raw_text = str(case.get("text") or "")
    result = {
        "model": model,
        "api_type": api_type,
        "prompt_name": prompt_name,
        "prompt_hash": prompt_hash(system_prompt),
        "scenario": scenario_id,
        "scenario_label": scenario["label"],
        "case_id": case.get("id"),
        "case_title": case.get("title"),
        "case_language": case.get("language"),
        "categories": case.get("categories") or [],
        "input": raw_text,
        "output": "",
        "status": "ok",
        "error": "",
        "latency_ms": None,
    }

    start = time.perf_counter()
    try:
        if dry_run:
            result["status"] = "dry_run"
            result["output"] = dry_output(case, scenario_id)
        else:
            estimated_tokens = min(4096, max(256, len(raw_text) * 4 + 300))
            result["output"] = client.complete_text(
                system_prompt,
                f"<speech_transcript>{raw_text}</speech_transcript>",
                LLMOptions(max_tokens=estimated_tokens, temperature=0),
            ).strip()
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    finally:
        result["latency_ms"] = round((time.perf_counter() - start) * 1000, 1)

    check_status = "ok" if result["status"] in ("ok", "dry_run") else result["status"]
    checks = auto_checks(result["output"], case, scenario_id, check_status)
    if result["status"] == "dry_run":
        checks["score"] = None
    result["auto_checks"] = checks["checks"]
    result["auto_score"] = checks["score"]
    result["issues"] = checks["issues"]
    return result


def summarize(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        groups[(item["model"], item["scenario"])].append(item)

    rows = []
    for (model, scenario), items in sorted(groups.items()):
        ok_items = [item for item in items if item["status"] == "ok"]
        score_values = [
            item["auto_score"]
            for item in ok_items
            if isinstance(item.get("auto_score"), (int, float))
        ]
        latencies = [
            item["latency_ms"]
            for item in ok_items
            if isinstance(item.get("latency_ms"), (int, float))
        ]
        rows.append({
            "model": model,
            "scenario": scenario,
            "scenario_label": SCENARIOS[scenario]["label"],
            "total": len(items),
            "ok": len(ok_items),
            "errors": len([item for item in items if item["status"] == "error"]),
            "avg_score": round(statistics.mean(score_values), 4) if score_values else None,
            "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        })
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_markdown(path: Path, run_meta: dict[str, Any], results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(results)
    lines = [
        "# Vox Polish Evaluation Report",
        "",
        f"- Run: `{run_meta['run_id']}`",
        f"- Prompt: `{run_meta['prompt_name']}` / `{run_meta['prompt_hash']}`",
        f"- Models: {', '.join(run_meta['models'])}",
        f"- Scenarios: {', '.join(run_meta['scenarios'])}",
        f"- Dry run: {run_meta['dry_run']}",
        "",
        "## Summary",
        "",
        "| Model | Scenario | OK / Total | Avg Score | Avg Latency |",
        "|---|---|---:|---:|---:|",
    ]
    for row in summary:
        score = "" if row["avg_score"] is None else f"{row['avg_score']:.2f}"
        latency = "" if row["avg_latency_ms"] is None else f"{row['avg_latency_ms']:.0f} ms"
        lines.append(
            f"| {row['model']} | {row['scenario_label']} | "
            f"{row['ok']} / {row['total']} | {score} | {latency} |"
        )

    issue_rows = [item for item in results if item.get("issues")]
    if issue_rows:
        lines.extend(["", "## Issues", ""])
        for item in issue_rows[:40]:
            issues = "; ".join(item.get("issues") or [])
            lines.append(f"- `{item['model']}` / `{item['scenario']}` / `{item['case_id']}`: {issues}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def write_html(path: Path, run_meta: dict[str, Any], results: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize(results)

    summary_rows = []
    for row in summary:
        score = "-" if row["avg_score"] is None else f"{row['avg_score']:.2f}"
        latency = "-" if row["avg_latency_ms"] is None else f"{row['avg_latency_ms']:.0f} ms"
        summary_rows.append(
            "<tr>"
            f"<td>{escape(row['model'])}</td>"
            f"<td>{escape(row['scenario_label'])}</td>"
            f"<td>{row['ok']} / {row['total']}</td>"
            f"<td>{score}</td>"
            f"<td>{row['errors']}</td>"
            f"<td>{latency}</td>"
            "</tr>"
        )

    result_cards = []
    for item in results:
        issue_text = "; ".join(item.get("issues") or [])
        score = item.get("auto_score")
        score_text = "dry" if score is None else f"{score:.2f}"
        tags = " ".join(
            f"<span>{escape(tag)}</span>"
            for tag in [item.get("case_language"), *(item.get("categories") or [])]
            if tag
        )
        status_class = "ok" if item["status"] == "ok" else ("dry" if item["status"] == "dry_run" else "err")
        result_cards.append(
            f"""
            <article class="result-card {status_class}" data-model="{escape(item['model'])}" data-scenario="{escape(item['scenario'])}" data-status="{escape(item['status'])}">
              <header>
                <div>
                  <h3>{escape(item['case_title'])}</h3>
                  <p>{escape(item['model'])} · {escape(item['scenario_label'])} · score {score_text} · {escape(item['latency_ms'])} ms</p>
                </div>
                <strong>{escape(item['status'])}</strong>
              </header>
              <div class="tags">{tags}</div>
              <section>
                <label>Input</label>
                <pre>{escape(item['input'])}</pre>
              </section>
              <section>
                <label>Output</label>
                <pre>{escape(item['output'] or item.get('error'))}</pre>
              </section>
              <section class="issues">
                <label>Checks</label>
                <p>{escape(issue_text or "No automatic issues.")}</p>
              </section>
            </article>
            """
        )

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vox Polish Evaluation</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f5;
      --panel: #ffffff;
      --ink: #19211f;
      --muted: #60706b;
      --line: #d9e1dc;
      --accent: #0f766e;
      --accent-2: #b45309;
      --bad: #b42318;
      --good: #0f7b49;
      --shadow: 0 16px 36px rgba(22, 35, 31, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.5;
    }}
    .shell {{ max-width: 1380px; margin: 0 auto; padding: 28px; }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr .8fr;
      gap: 24px;
      align-items: end;
      margin-bottom: 22px;
    }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    .hero p {{ margin: 0; color: var(--muted); }}
    .meta {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 16px;
      box-shadow: var(--shadow);
    }}
    .meta div {{ display: flex; justify-content: space-between; gap: 18px; padding: 3px 0; }}
    .meta span:first-child {{ color: var(--muted); }}
    .toolbar {{
      position: sticky;
      top: 0;
      z-index: 5;
      display: grid;
      grid-template-columns: 1fr repeat(3, minmax(150px, 220px));
      gap: 10px;
      padding: 12px 0;
      background: rgba(246, 247, 245, .92);
      backdrop-filter: blur(10px);
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      color: var(--ink);
      background: var(--panel);
      font: inherit;
    }}
    .summary {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      box-shadow: var(--shadow);
      margin: 10px 0 24px;
    }}
    .summary th, .summary td {{
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      white-space: nowrap;
    }}
    .summary th {{ color: var(--muted); font-weight: 600; background: #edf3f0; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }}
    .result-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 16px;
      box-shadow: var(--shadow);
    }}
    .result-card.err {{ border-left-color: var(--bad); }}
    .result-card.dry {{ border-left-color: var(--accent-2); }}
    .result-card header {{ display: flex; align-items: start; justify-content: space-between; gap: 12px; }}
    .result-card h3 {{ margin: 0 0 4px; font-size: 17px; }}
    .result-card header p {{ margin: 0; color: var(--muted); font-size: 13px; }}
    .result-card header strong {{
      color: var(--panel);
      background: var(--accent);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .result-card.err header strong {{ background: var(--bad); }}
    .result-card.dry header strong {{ background: var(--accent-2); }}
    .tags {{ margin: 10px 0; display: flex; flex-wrap: wrap; gap: 6px; }}
    .tags span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 2px 8px;
      color: var(--muted);
      font-size: 12px;
      background: #f9fbfa;
    }}
    section {{ margin-top: 12px; }}
    label {{ display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      background: #f7faf8;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      font-size: 14px;
    }}
    .issues p {{ margin: 0; color: var(--muted); }}
    .hidden {{ display: none; }}
    @media (max-width: 860px) {{
      .shell {{ padding: 18px; }}
      .hero {{ grid-template-columns: 1fr; }}
      .toolbar {{ grid-template-columns: 1fr; position: static; }}
      .grid {{ grid-template-columns: 1fr; }}
      .summary {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1>Vox Polish Evaluation</h1>
        <p>润色、翻译和双语输出的模型对比报告。</p>
      </div>
      <div class="meta">
        <div><span>Run</span><strong>{escape(run_meta['run_id'])}</strong></div>
        <div><span>Prompt</span><strong>{escape(run_meta['prompt_name'])} / {escape(run_meta['prompt_hash'])}</strong></div>
        <div><span>Models</span><strong>{escape(', '.join(run_meta['models']))}</strong></div>
        <div><span>Dry run</span><strong>{escape(run_meta['dry_run'])}</strong></div>
      </div>
    </section>

    <section class="toolbar">
      <input id="q" type="search" placeholder="Search case, input, output...">
      <select id="model"><option value="">All models</option></select>
      <select id="scenario"><option value="">All scenarios</option></select>
      <select id="status"><option value="">All statuses</option><option value="ok">ok</option><option value="error">error</option><option value="dry_run">dry_run</option></select>
    </section>

    <table class="summary">
      <thead><tr><th>Model</th><th>Scenario</th><th>OK / Total</th><th>Avg Score</th><th>Errors</th><th>Avg Latency</th></tr></thead>
      <tbody>{''.join(summary_rows)}</tbody>
    </table>

    <section id="cards" class="grid">
      {''.join(result_cards)}
    </section>
  </main>
  <script>
    const cards = Array.from(document.querySelectorAll('.result-card'));
    const model = document.querySelector('#model');
    const scenario = document.querySelector('#scenario');
    const status = document.querySelector('#status');
    const q = document.querySelector('#q');

    function fill(select, attr) {{
      const values = Array.from(new Set(cards.map(card => card.dataset[attr]).filter(Boolean))).sort();
      for (const value of values) {{
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
      }}
    }}

    function applyFilters() {{
      const text = q.value.trim().toLowerCase();
      for (const card of cards) {{
        const ok = (!model.value || card.dataset.model === model.value)
          && (!scenario.value || card.dataset.scenario === scenario.value)
          && (!status.value || card.dataset.status === status.value)
          && (!text || card.textContent.toLowerCase().includes(text));
        card.classList.toggle('hidden', !ok);
      }}
    }}

    fill(model, 'model');
    fill(scenario, 'scenario');
    [model, scenario, status, q].forEach(el => el.addEventListener('input', applyFilters));
  </script>
</body>
</html>
"""
    path.write_text(html_doc, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Vox polishing prompts and models.")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml.")
    parser.add_argument("--profile", default="default", help="LLM profile name in config.yaml.")
    parser.add_argument("--endpoint", default="", help="Override profile endpoint/base URL.")
    parser.add_argument("--api-key-env", default="", help="Override profile API key environment variable.")
    parser.add_argument("--api-key", default="", help="Override profile API key. Prefer --api-key-env.")
    parser.add_argument("--host-header", default="", help="Send this HTTP Host header for direct IP endpoints.")
    parser.add_argument("--tls-no-verify", action="store_true", help="Disable TLS verification for direct IP endpoints.")
    parser.add_argument("--cases", default="eval/cases.yaml", help="Evaluation cases YAML.")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS), help="Comma-separated model names.")
    parser.add_argument(
        "--scenarios",
        default="polish,translate_en,translate_en_original,translate_zh,translate_zh_original",
        help=f"Comma-separated scenarios: {', '.join(SCENARIOS)}",
    )
    parser.add_argument(
        "--api-type",
        default="profile",
        choices=["profile", "auto", "openai_compatible", "openai_responses", "anthropic", "azure_openai"],
        help="API type override. profile uses the selected config profile provider.",
    )
    parser.add_argument("--prompt-file", default="", help="Optional base prompt file. Empty uses src.polisher default.")
    parser.add_argument("--prompt-name", default="default", help="Prompt name shown in reports.")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of cases before scenario filtering.")
    parser.add_argument("--case-id", action="append", default=[], help="Run only a specific case id. Can repeat.")
    parser.add_argument("--dry-run", action="store_true", help="Do not call an API; generate a report skeleton.")
    parser.add_argument("--skip-validate", action="store_true", help="Skip provider validation before running.")
    parser.add_argument("--output-dir", default="eval/results", help="JSONL output directory.")
    parser.add_argument("--report-dir", default="eval/reports", help="HTML/Markdown report directory.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    models = parse_csv(args.models)
    scenarios = parse_csv(args.scenarios)
    unknown = [scenario for scenario in scenarios if scenario not in SCENARIOS]
    if unknown:
        raise SystemExit(f"Unknown scenario(s): {', '.join(unknown)}")

    case_path = (ROOT / args.cases).resolve()
    cases = load_cases(case_path, args.case_id or None, args.limit or None)
    if not cases:
        raise SystemExit("No evaluation cases selected.")

    base_prompt = ""
    if args.prompt_file:
        base_prompt = (ROOT / args.prompt_file).read_text(encoding="utf-8")

    prompt_preview = build_prompt(base_prompt)
    prompt_digest = prompt_hash(prompt_preview)

    base_profile: dict[str, Any] = {}
    if not args.dry_run:
        config = load_yaml((ROOT / args.config).resolve())
        base_profile = get_llm_profile_config(config, args.profile)
        if args.endpoint:
            base_profile["endpoint"] = args.endpoint
            base_profile.pop("base_url", None)
        if args.api_key_env:
            base_profile["api_key_env"] = args.api_key_env
            base_profile.pop("api_key", None)
        if args.api_key:
            base_profile["api_key"] = args.api_key
            base_profile.pop("api_key_env", None)

    results: list[dict[str, Any]] = []
    for model in models:
        client = None
        runtime_api_type = args.api_type
        if not args.dry_run:
            try:
                if args.host_header or args.tls_no_verify:
                    client, runtime_api_type, validation_response = direct_client_for_model(
                        base_profile,
                        model,
                        args.api_type,
                        args.host_header,
                        not args.tls_no_verify,
                        args.skip_validate,
                    )
                else:
                    runtime_profile, validation_response = profile_for_model(
                        base_profile,
                        model,
                        args.api_type,
                        args.skip_validate,
                    )
                    runtime_api_type = runtime_profile.get("provider", args.api_type)
                    client = create_llm_client(runtime_profile)
                print(f"[eval] {model}: provider={runtime_api_type}, validation={validation_response}")
            except Exception as e:
                print(f"[eval] {model}: provider setup failed: {e}")
                for scenario_id in scenarios:
                    for case in cases:
                        if not scenario_applies(case, scenario_id):
                            continue
                        results.append({
                            "model": model,
                            "api_type": args.api_type,
                            "prompt_name": args.prompt_name,
                            "prompt_hash": prompt_digest,
                            "scenario": scenario_id,
                            "scenario_label": SCENARIOS[scenario_id]["label"],
                            "case_id": case.get("id"),
                            "case_title": case.get("title"),
                            "case_language": case.get("language"),
                            "categories": case.get("categories") or [],
                            "input": case.get("text") or "",
                            "output": "",
                            "status": "error",
                            "error": str(e),
                            "latency_ms": None,
                            "auto_checks": [{"name": "request_ok", "ok": False, "detail": str(e)}],
                            "auto_score": 0.0,
                            "issues": [str(e)],
                        })
                continue

        for scenario_id in scenarios:
            for case in cases:
                if not scenario_applies(case, scenario_id):
                    continue
                result = run_case(
                    client,
                    model,
                    runtime_api_type,
                    args.prompt_name,
                    base_prompt,
                    case,
                    scenario_id,
                    args.dry_run,
                )
                results.append(result)
                print(
                    f"[eval] {model} {scenario_id} {case.get('id')}: "
                    f"{result['status']} score={result.get('auto_score')}"
                )

    run_meta = {
        "run_id": run_id,
        "models": models,
        "scenarios": scenarios,
        "prompt_name": args.prompt_name,
        "prompt_hash": prompt_digest,
        "dry_run": args.dry_run,
        "case_count": len(cases),
    }

    result_path = ROOT / args.output_dir / f"{run_id}.jsonl"
    html_path = ROOT / args.report_dir / f"{run_id}.html"
    md_path = ROOT / args.report_dir / f"{run_id}.md"
    latest_html = ROOT / args.report_dir / "latest.html"
    latest_md = ROOT / args.report_dir / "latest.md"

    write_jsonl(result_path, results)
    write_html(html_path, run_meta, results)
    write_markdown(md_path, run_meta, results)
    latest_html.write_text(html_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_md.write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"[eval] wrote {result_path}")
    print(f"[eval] wrote {html_path}")
    print(f"[eval] wrote {md_path}")
    print(f"[eval] latest report: {latest_html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
