#!/usr/bin/env python3
"""Build a weekly Fact Pack and optionally call an LLM for the Outlook report."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyst.fact_pack import build_fact_pack, fact_pack_to_markdown
from scripts.analyst.language import (
    DEFAULT_LANG,
    LanguageProfile,
    apply_language,
    report_suffix,
    resolve_language,
)
from scripts.analyst.llm_client import complete, load_dotenv
from scripts.analyst.report_lint import lint_report
from scripts.extract.config import GOLD_MART_DIR, project_root_for_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PROMPT_PATH = REPO_ROOT / "docs" / "analyst" / "prompts" / "weekly_soros_prompt.md"
SEMANTICS_DIR = REPO_ROOT / "docs" / "analyst" / "semantics"
DEFAULT_REPORTS_DIR = project_root_for_data() / "reports" / "weekly"
CONTROL_FILES = (
    SEMANTICS_DIR / "macro_textbook.md",
    SEMANTICS_DIR / "metrics.yml",
    SEMANTICS_DIR / "control_interactions.yml",
)


def current_iso_week() -> tuple[int, int]:
    today = date.today()
    iso = today.isocalendar()
    return iso.year, iso.week


def load_control_lane() -> str:
    chunks = ["# Control Lane (textbook + metric meanings + interactions)\n"]
    for path in CONTROL_FILES:
        if path.exists():
            chunks.append(f"## File: {path.name}\n\n{path.read_text().rstrip()}\n")
    return "\n".join(chunks)


def assemble_system_prompt(contract: str, profile: LanguageProfile) -> str:
    localized = apply_language(contract, profile)
    return localized.rstrip() + "\n\n---\n\n" + load_control_lane()


def assemble_user_message(pack: dict, pack_md: str, profile: LanguageProfile) -> str:
    return (
        "The Fact Pack below is pre-computed from gold/mart. "
        "Every count, share, HCM clock, and fact_id is already verified. "
        f"{profile.user_preamble} "
        "After reviewing this week, write the next-week look-ahead only from the next_week block. "
        "Section VIII: Soros swing rules — no new primary entries in red windows. "
        "Do not recalculate numbers.\n\n"
        f"{pack_md}\n\n"
        "## Fact Pack JSON\n\n"
        "```json\n"
        f"{json.dumps(pack, indent=2, ensure_ascii=False)}\n"
        "```\n"
    )


def attach_model_credit(
    text: str,
    *,
    model: str,
    language: str | None = DEFAULT_LANG,
) -> str:
    """Keep a single closing line; append model: slug (no extra heading)."""
    profile = resolve_language(language)
    credit = f" model: `{model}`"
    body = text.rstrip()
    body = re.sub(
        r"\n+---\n+\n*### Model đã viết báo cáo[\s\S]*$",
        "",
        body,
    )
    lines = body.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        raw = lines[i].strip()
        if not raw:
            continue
        if any(marker in raw for marker in profile.closing_markers):
            core = raw.strip("*").rstrip()
            core = re.sub(r"\s*model:\s*`[^`]+`\s*$", "", core, flags=re.I)
            core = re.sub(r"\s*model:\s*\S+\s*$", "", core, flags=re.I)
            if not any(marker in core for marker in profile.closing_markers):
                core = profile.closing_line
            lines[i] = core + credit
            return "\n".join(lines).rstrip()
        break
    return body + "\n" + profile.closing_line + credit


def write_report(
    text: str,
    out_path: Path,
    *,
    week_label: str,
    provider: str,
    model: str,
    dry_run: bool,
    language: str | None = DEFAULT_LANG,
) -> None:
    header = (
        f"<!-- generated: {week_label} | provider={provider} | model={model} "
        f"| lang={resolve_language(language).code} | dry_run={dry_run} -->\n\n"
    )
    body = text.rstrip()
    if not dry_run:
        body = attach_model_credit(body, model=model, language=language)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + body + "\n")


def run_outlook(
    *,
    year: int,
    week: int,
    mart_dir: Path = GOLD_MART_DIR,
    prompt: Path = PROMPT_PATH,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    provider: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    timeout: int = 180,
    suffix: str | None = None,
    skip_lint: bool = False,
    lang: str = DEFAULT_LANG,
    institutional: dict | None = None,
    skip_llm: bool = False,
) -> dict:
    """C+D — Fact Pack then LLM outlook. Returns paths and lint status."""
    profile = resolve_language(lang)
    pack = build_fact_pack(year, week, mart_dir, institutional=institutional)
    pack_md = fact_pack_to_markdown(pack)
    system = assemble_system_prompt(prompt.read_text(), profile)
    user = assemble_user_message(pack, pack_md, profile)
    week_label = pack["week_label"]
    stem = f"{week_label}-macro-outlook.{report_suffix(profile.code, suffix)}"

    pack_json_path = reports_dir / f"{week_label}-fact-pack.json"
    pack_md_path = reports_dir / f"{week_label}-fact-pack.md"
    pack_json_path.parent.mkdir(parents=True, exist_ok=True)
    pack_json_path.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n")
    pack_md_path.write_text(pack_md)
    logger.info("Wrote fact pack %s and %s", pack_json_path, pack_md_path)

    result = {
        "week_label": week_label,
        "fact_pack_json": str(pack_json_path),
        "fact_pack_md": str(pack_md_path),
        "dry_run": dry_run,
        "lint": "skipped",
        "llm": "skipped" if skip_llm else "executed",
        "report": None,
        "provider": provider,
        "model": model,
        "lang": profile.code,
        "exit_code": 0,
    }

    if skip_llm:
        logger.info("Fact pack ready (LLM outlook skipped: 100% deterministic mode)")
        return result

    if dry_run:
        out_path = reports_dir / f"{stem}.dry-run.md"
        write_report(
            f"# DRY RUN prompt for {week_label}\n\n## System\n\n{system}\n\n## User\n\n{user}",
            out_path,
            week_label=week_label,
            provider=provider or "none",
            model=model or "none",
            dry_run=True,
            language=profile.code,
        )
        logger.info("Dry-run prompt written to %s", out_path)
        result["report"] = str(out_path)
        return result

    text, used_provider, used_model = complete(
        system,
        user,
        provider=provider,
        model=model,
        timeout=timeout,
    )
    out_path = reports_dir / f"{stem}.md"
    write_report(
        text,
        out_path,
        week_label=week_label,
        provider=used_provider,
        model=used_model,
        dry_run=False,
        language=profile.code,
    )
    logger.info("Report written to %s (%s / %s)", out_path, used_provider, used_model)
    result["report"] = str(out_path)
    result["provider"] = used_provider
    result["model"] = used_model

    if not skip_lint:
        issues = lint_report(text, pack)
        lint_path = reports_dir / f"{stem}.lint.txt"
        if issues:
            lint_path.write_text("FAIL\n" + "\n".join(f"- {i}" for i in issues) + "\n")
            logger.warning("Lint FAIL (%s issues) → %s", len(issues), lint_path)
            for item in issues:
                logger.warning("  %s", item)
            result["lint"] = "fail"
            result["lint_path"] = str(lint_path)
            result["lint_issues"] = issues
            result["exit_code"] = 2
            return result
        lint_path.write_text("PASS\n")
        logger.info("Lint PASS")
        result["lint"] = "pass"
        result["lint_path"] = str(lint_path)
    return result


def main() -> int:
    load_dotenv()
    iso_year, iso_week = current_iso_week()
    parser = argparse.ArgumentParser(description="Run the weekly Soros-style macro outlook.")
    parser.add_argument("--year", type=int, default=iso_year)
    parser.add_argument("--week", type=int, default=iso_week, help="ISO week number")
    parser.add_argument("--mart-dir", type=Path, default=GOLD_MART_DIR)
    parser.add_argument("--prompt", type=Path, default=PROMPT_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--provider", choices=("openrouter", "google"))
    parser.add_argument("--model", help="Override OPENROUTER_MODEL or GEMINI_MODEL")
    parser.add_argument("--dry-run", action="store_true", help="Write assembled prompt only")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument(
        "--suffix",
        help="Append to output stem, e.g. ling-fin → 2026-W36-macro-outlook.ling-fin.md",
    )
    parser.add_argument("--skip-lint", action="store_true", help="Do not lint the generated report")
    parser.add_argument(
        "--skip-llm",
        "--fact-pack-only",
        dest="skip_llm",
        action="store_true",
        help="Build Fact Pack JSON & MD only (100% deterministic, skip LLM call)",
    )
    parser.add_argument(
        "--lang",
        default=os.environ.get("REPORT_LANG", DEFAULT_LANG),
        help="Report language: vi, en, or any name (ja, es, …). Default: vi or REPORT_LANG",
    )
    args = parser.parse_args()
    result = run_outlook(
        year=args.year,
        week=args.week,
        mart_dir=args.mart_dir,
        prompt=args.prompt,
        reports_dir=args.reports_dir,
        provider=args.provider,
        model=args.model,
        dry_run=args.dry_run,
        timeout=args.timeout,
        suffix=args.suffix,
        skip_lint=args.skip_lint,
        lang=args.lang,
        skip_llm=args.skip_llm,
    )
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
