# Forex calendar → Kimball mart → weekly macro outlook

Deterministic ETL for the Forex Factory calendar, plus a **linted** weekly brief for swing trading USD / EUR / GBP / JPY.

The LLM never invents the calendar. Python computes the Fact Pack. The model only reasons. A linter rejects numbers that are not in the pack.

**Samples:** [English](reports/weekly/2026-W36-macro-outlook.en.md) · [Tiếng Việt](reports/weekly/2026-W36-macro-outlook.vi.md)

```text
nfs.faireconomy.media (this week, no WARP)
        │
        ▼
 bronze → silver SSOT → gold Kimball mart
        │
        ▼
 Fact Pack (counts, clashes, HCM clocks, fact_id)
        │
        ▼
 LLM outlook (--lang en|vi|…)  →  report lint
```

## What you get

- **Medallion + Kimball** — bronze landing, silver events, gold dims/facts, optional Google Calendar CSV
- **ABCD weekly job** — fetch → ingest → Fact Pack → outlook. Fail-stop: no LLM if fetch/transform fails
- **Soros contract** — hypothesis + falsification; no new primary swing entries in red windows
- **Language flag** — `--lang en`, `--lang vi`, or any language name

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_weekly_abcd.py --fmt csv
```

**100% Deterministic by default:** Generates Silver conformed partitions, Gold Kimball Mart, Google Calendar CSVs, and the weekly **Fact Pack** (`reports/weekly/{YYYY}-W{WW}-fact-pack.{json,md}`). Zero external LLM calls or API keys required.

To run the optional LLM Outlook Report locally (or provide `.env` keys):

```bash
cp .env.template .env
python scripts/run_weekly_abcd.py --fmt csv --with-llm --lang en
```

Output with `--with-llm`: `reports/weekly/{YYYY}-W{WW}-macro-outlook.{lang}.md`

| You fill in | Where |
|---|---|
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) |
| `OPENROUTER_MODEL` | optional. Models come from the shared router at `FM_OPENROUTER_TOOLS`; this model is tried last |
| `REPORT_LANG` | optional, `en` or `vi` |

When `FM_OPENROUTER_TOOLS` is unset, the weekly outlook uses the local fallback list in `scripts/analyst/llm_client.py`.

To keep code in one checkout and `data/` + `reports/` elsewhere (for example a separate data repo), export `FX_DESK_DATA_ROOT` to that project root before starting Python. Point `FX_DESK_DOTENV` at the `.env` that holds API keys.

## Layout

```text
scripts/extract/     fetch this-week + Cloudflare playbook
scripts/transform/   landing → silver → Kimball
scripts/analyst/     Fact Pack, lint, language, LLM client
scripts/run_weekly_abcd.py
data/{bronze,silver,gold}/
reports/weekly/      sample outlooks (en / vi)
docs/analyst/        prompt + Control Lane semantics
```

## Tests

```bash
pip install -r requirements.txt
python -m pytest -q -m "not integration"
```

## Docs

[Index](docs/INDEX.md) · [Scrape strategy](docs/scrape_strategy.md) · [Analyst roadmap](docs/analyst-roadmap.md)

MIT — see [LICENSE](LICENSE). Do not commit `.env`.
