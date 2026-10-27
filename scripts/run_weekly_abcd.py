#!/usr/bin/env python3
"""ABCD weekly pipeline: fetch this week → gold mart → Fact Pack → outlook.

A  ``fetch_weekly.py`` — nfs.faireconomy.media this-week export (no WARP, no HTML).
A2 ``backfill_actuals.py`` — monthly HTML re-scrape, the only source of printed
   ``actual``. Four Cloudflare-paced requests per month (red/orange/yellow/gray).
   Non-fatal: a failure leaves stored actuals untouched.
B  landing → coalesce upsert into silver ``YYYY_MM.csv`` → Kimball mart.
C0 ICT Institutional Layer (COT / SMT Sunday watchlist / Seasonal+Quarterly).
C  Fact Pack from gold/mart (+ institutional merge).
D  LLM outlook + lint. Fail-stop: A or B fail ⇒ do not call the LLM.

Fetch settings match ``docs/scrape_strategy.md``: strategy=http, firefox135,
human_delay, CSV first, ~2 requests / 5 minutes. Do not fetch historical months.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.analyst.llm_client import load_dotenv


def _bootstrap_env() -> None:
    for i, arg in enumerate(sys.argv):
        if arg == "--data-root" and i + 1 < len(sys.argv):
            os.environ["FX_DESK_DATA_ROOT"] = str(Path(sys.argv[i + 1]).expanduser().resolve())
            break
        if arg.startswith("--data-root="):
            os.environ["FX_DESK_DATA_ROOT"] = str(Path(arg.split("=", 1)[1]).expanduser().resolve())
            break
    dotenv_path = os.environ.get("FX_DESK_DOTENV", "").strip()
    load_dotenv(Path(dotenv_path) if dotenv_path else None)


_bootstrap_env()

try:
    from scripts.analyst.ict_fact_pack import run_ict_pipeline
except ImportError:
    run_ict_pipeline = None

from scripts.analyst.language import DEFAULT_LANG
from scripts.analyst.run_weekly_report import current_iso_week, run_outlook
from scripts.extract.backfill_actuals import backfill_actuals
from scripts.extract.config import GOLD_MART_DIR, project_root_for_data
from scripts.extract.fetch_weekly import fetch_this_week
from scripts.transform.validate_coverage import check_impact_coverage
from scripts.transform.to_google_calendar import DEFAULT_SOURCE_TZ
from scripts.transform.weekly_ingest import WEEKLY_BRONZE_DEFAULT, ingest_weekly_bronze

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_abcd(
    *,
    fmt: str = "csv",
    skip_fetch: bool = False,
    fallback: bool = False,
    source_timezone: str = DEFAULT_SOURCE_TZ,
    export_clock_tz: str = "UTC",
    write_gcal: bool = True,
    year: int | None = None,
    week: int | None = None,
    dry_run: bool = False,
    skip_report: bool = False,
    with_llm: bool = False,
    skip_lint: bool = False,
    skip_ict: bool = False,
    skip_actual_backfill: bool = False,
    backfill_strategy: str = "http",
    provider: str | None = None,
    model: str | None = None,
    timeout: int = 180,
    suffix: str | None = None,
    reports_dir: Path | None = None,
    mart_dir: Path = GOLD_MART_DIR,
    lang: str = DEFAULT_LANG,
) -> dict:
    summary: dict = {"ok": False, "stopped_at": None}

    if skip_fetch:
        bronze = WEEKLY_BRONZE_DEFAULT
        if not bronze.exists():
            raise FileNotFoundError(
                f"--skip-fetch but missing {bronze}. Run without --skip-fetch first."
            )
        summary["A"] = {"skipped": True, "csv": str(bronze)}
        logger.info("A skipped — using existing %s", bronze)
    else:
        logger.info("A — fetch this-week export (%s), no WARP, fallback=%s", fmt, fallback)
        summary["A"] = fetch_this_week(fmt=fmt, fallback=fallback)
        logger.info(
            "A ok — %s rows via %s",
            summary["A"]["rows"],
            summary["A"]["method"],
        )

    # A2 must run before B so the mart rebuild at the end of B already sees the
    # freshly backfilled actuals. Non-fatal by design: losing this month's
    # scrape must not block the report, and stored actuals are never erased.
    if skip_actual_backfill:
        summary["A2"] = {"skipped": True}
        logger.info("A2 skipped — silver keeps whatever actuals it already has")
    else:
        try:
            logger.info("A2 — backfill printed actuals from monthly HTML")
            summary["A2"] = backfill_actuals(
                fetch=not skip_fetch,
                strategy=backfill_strategy,
                write_gold_gcal=write_gcal,
            )
            for month in summary["A2"]["months"]:
                logger.info(
                    "A2 %s.%s — coverage=%s upsert=%s",
                    month.get("month"),
                    month.get("year"),
                    month.get("coverage"),
                    month.get("silver_upsert"),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("A2 failed — continuing without fresh actuals: %s", exc)
            summary["A2"] = {"ok": False, "error": str(exc)}

    logger.info("B — bronze weekly → silver → mart")
    summary["B"] = ingest_weekly_bronze(
        summary["A"].get("csv") or str(WEEKLY_BRONZE_DEFAULT),
        source_timezone=source_timezone,
        export_clock_tz=export_clock_tz,
        write_gcal=write_gcal,
        rebuild_mart=True,
        mart_dir=mart_dir,
    )
    logger.info(
        "B ok — %s (%s silver rows)",
        summary["B"]["week_label"],
        summary["B"]["rows"],
    )

    summary["validate"] = check_impact_coverage()
    if not summary["validate"]["ok"]:
        logger.warning(
            "B — %s partition(s) missing an impact layer; holidays will be under-reported",
            len(summary["validate"]["warnings"]),
        )

    iso_year = year if year is not None else int(summary["B"]["iso_year"])
    iso_week = week if week is not None else int(summary["B"]["iso_week"])
    summary["week_label"] = f"{iso_year}-W{iso_week:02d}"

    reports = reports_dir or (project_root_for_data() / "reports" / "weekly")
    institutional = None
    if skip_ict or run_ict_pipeline is None:
        summary["C0"] = {
            "skipped": True,
            "reason": "not_installed" if run_ict_pipeline is None else "skipped",
        }
        if run_ict_pipeline is not None and not skip_ict:
            logger.info("C0 skipped — no ICT institutional layer")
    else:
        logger.info("C0 — ICT Institutional (COT / SMT / Seasonal)")
        try:
            ict = run_ict_pipeline(
                iso_year,
                iso_week,
                skip_fetch=skip_fetch,
                reports_dir=reports,
            )
            summary["C0"] = {k: v for k, v in ict.items() if k != "pack"}
            institutional = ict.get("pack")
            logger.info(
                "C0 ok — %s / %s",
                summary["C0"].get("ict_fact_pack_json"),
                summary["C0"].get("institutional_md"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("C0 failed (continuing without institutional): %s", exc)
            summary["C0"] = {"ok": False, "error": str(exc)}

    if skip_report:
        summary["C"] = {"skipped": True}
        summary["D"] = {"skipped": True}
        summary["ok"] = True
        summary["stopped_at"] = "C0" if not (skip_ict or run_ict_pipeline is None) else "B"
        return summary

    logger.info("C — Fact Pack for %s", summary["week_label"])
    outlook = run_outlook(
        year=iso_year,
        week=iso_week,
        mart_dir=mart_dir,
        reports_dir=reports,
        provider=provider,
        model=model,
        dry_run=dry_run,
        timeout=timeout,
        suffix=suffix,
        skip_lint=skip_lint,
        lang=lang,
        institutional=institutional,
        skip_llm=not with_llm and not dry_run,
    )
    summary["C"] = {
        "fact_pack_json": outlook["fact_pack_json"],
        "fact_pack_md": outlook["fact_pack_md"],
    }

    if not with_llm and not dry_run:
        summary["D"] = {
            "skipped": True,
            "reason": "LLM generation paused / delegated to external layer (enable with --with-llm)",
        }
        summary["ok"] = True
        summary["stopped_at"] = "C"
        logger.info(
            "C ok — Fact Pack generated (D skipped: 100% deterministic pipeline, use --with-llm for LLM report)"
        )
        return summary

    summary["D"] = outlook
    summary["ok"] = outlook["exit_code"] == 0
    summary["stopped_at"] = "D"
    return summary


def main() -> int:
    today_year, today_week = current_iso_week()
    parser = argparse.ArgumentParser(
        description="ABCD: fetch this week (no WARP) → mart → weekly outlook",
    )
    parser.add_argument("--fmt", choices=("csv", "xml", "json"), default="csv")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse data/bronze/weekly/thisweek.csv (no network)",
    )
    parser.add_argument(
        "--fallback-formats",
        action="store_true",
        help="If CSV fails, try XML then JSON (burns the ~2/5 min quota)",
    )
    parser.add_argument("--source-tz", default=DEFAULT_SOURCE_TZ)
    parser.add_argument(
        "--export-clock-tz",
        default="UTC",
        help="Clock TZ of the faireconomy export (UTC). Converted to US Eastern for bronze.",
    )
    parser.add_argument("--no-gcal", action="store_true")
    parser.add_argument("--year", type=int, help="Override report ISO year (default: from fetch)")
    parser.add_argument("--week", type=int, help="Override report ISO week (default: from fetch)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Enable Step D: Call LLM to generate weekly macro outlook (default: False, pipeline is 100%% deterministic)",
    )
    parser.add_argument("--skip-report", action="store_true", help="Stop after B/C0 (no Fact Pack or LLM)")
    parser.add_argument(
        "--skip-ict",
        action="store_true",
        help="Skip C0 ICT Institutional Layer (COT/SMT/Seasonal)",
    )
    parser.add_argument(
        "--skip-actual-backfill",
        action="store_true",
        help="Skip A2 monthly HTML re-scrape (saves 4 Cloudflare-paced requests per month)",
    )
    parser.add_argument(
        "--backfill-strategy",
        choices=("auto", "http", "browser", "stealth"),
        default="http",
        help="Fetch strategy for A2. See docs/scrape_strategy.md",
    )
    parser.add_argument("--skip-lint", action="store_true")
    parser.add_argument("--provider", choices=("openrouter", "google"))
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--suffix")
    parser.add_argument(
        "--lang",
        default=os.environ.get("REPORT_LANG", DEFAULT_LANG),
        help="Report language: vi, en, or any name (ja, es, …). Default: vi or REPORT_LANG",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        help="Project root whose data/ tree to use (default: repo root or FX_DESK_DATA_ROOT)",
    )
    parser.add_argument("--reports-dir", type=Path)
    parser.add_argument("--mart-dir", type=Path, default=GOLD_MART_DIR)
    args = parser.parse_args()

    try:
        summary = run_abcd(
            fmt=args.fmt,
            skip_fetch=args.skip_fetch,
            fallback=args.fallback_formats,
            source_timezone=args.source_tz,
            export_clock_tz=args.export_clock_tz,
            write_gcal=not args.no_gcal,
            year=args.year,
            week=args.week,
            dry_run=args.dry_run,
            skip_report=args.skip_report,
            with_llm=args.with_llm,
            skip_ict=args.skip_ict,
            skip_lint=args.skip_lint,
            skip_actual_backfill=args.skip_actual_backfill,
            backfill_strategy=args.backfill_strategy,
            provider=args.provider,
            model=args.model,
            timeout=args.timeout,
            suffix=args.suffix,
            lang=args.lang,
            reports_dir=args.reports_dir,
            mart_dir=args.mart_dir,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("ABCD stopped: %s", exc)
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps(summary, indent=2, default=str))
    if not summary.get("ok"):
        d_code = (summary.get("D") or {}).get("exit_code")
        return int(d_code) if d_code else 1
    logger.info(
        "ABCD done for %s (today is %s-W%02d)",
        summary.get("week_label"),
        today_year,
        today_week,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
