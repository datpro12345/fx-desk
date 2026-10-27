# Scrape strategy — Forex Factory + Cloudflare

Canonical playbook. Implemented in `scripts/extract/client.py` + `config.py`. Experiments: `docs/LOG.md`.

## Decision (reuse this)

1. **Egress first.** VN residential IP is TLS-reset on `www.forexfactory.com`. Open **Cloudflare WARP → Traffic and DNS (UDP)** (or residential proxy `FF_HTTP_PROXY`). Confirm FF HTML 200 before fetching months.
2. **This week only:** `https://nfs.faireconomy.media/ff_calendar_thisweek.{csv,xml,json}` — no WARP, no HTML. Rate-limit ~2 / 5 min. Export clocks are **UTC** (NFP `12:30pm` = 8:30am ET). CLI: `scripts/extract/fetch_weekly.py` or ABCD `scripts/run_weekly_abcd.py`.
3. **Historical / YTD:** HTML calendar, **four URLs per month** (`impacts=3|2|1|0` = red|orange|yellow|gray/holiday). `curl_cffi` + `impersonate=firefox135`. Pace `--gap 45` + jitter 2–5s. Save `.html`. Parse with `parse_calendar_html`. Holiday rows (impact 0) are session closures; without them Silver/mart cannot flag thin-liquidity days per currency.
4. **Do not** depend on dated XML (`ff_calendar_monthddyyyy.xml`) — CDN 404. **Do not** expect CloudScraper / undetected-chrome / UA rotation to unstick a TLS-reset IP.

## Fetch stack (`strategy=auto`)

`curl_cffi` → `cloudscraper` → Playwright → optional undetected-chrome. For YTD with WARP up, use `--strategy http` (stop after curl_cffi/cloudscraper).

## Commands

```bash
# This week only (no WARP): A fetch → B silver/mart → C Fact Pack → D outlook
.venv/bin/python scripts/run_weekly_abcd.py --fmt csv
.venv/bin/python scripts/extract/fetch_weekly.py --fmt csv
.venv/bin/python scripts/extract/fetch_bronze_months.py --year 2026 --months jan feb mar --gap 45 --strategy http
.venv/bin/python scripts/run_medallion.py --year 2026   # bronze raw → silver → gold + mart
```

Stop on TLS reset / persistent 403. Rebuild offline: `build_month_from_markdown.py` (HTML or markdown dumps).
