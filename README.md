# GAParser

Config-driven GA4 reporting CLI for multi-property website summaries.

## What it does

- Loads website-to-property mappings from `config/properties.json`
- Pulls `activeUsers` and `organicGoogleSearchImpressions` by default
- Keeps impressions strictly on `organicGoogleSearchImpressions` (no `screenPageViews` fallback)
- Aggregates impressions using the `landingPagePlusQueryString` breakdown to align with GA4 Search Console traffic reports
- Prints a formatted summary
- Optionally exports to `txt`, `csv`, and `json`

## Project layout

- `src/ga_reporter/` application code
- `config/` property config files
- `reports/` generated outputs
- `tests/` unit tests

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configure properties

1. Copy `config/properties.example.json` to `config/properties.json`
2. Fill in your GA4 property IDs

## Authentication

Use one of:

- `--service-account path\to\service_account.json`
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable

Also add the service account email to each GA4 property with at least Viewer access.

## Run

Custom range:

```powershell
python ga_summary.py --filter range --start 2026-02-01 --end 2026-02-15
```

Preset filters:

```powershell
python ga_summary.py --filter daily
python ga_summary.py --filter weekly
python ga_summary.py --filter monthly
```

Use the organic impressions metric explicitly:

```powershell
python ga_summary.py --filter weekly --impressions-metric organicGoogleSearchImpressions
```

Single command with numbered menu:

```powershell
python ga_summary.py --menu
```

With exports:

```powershell
python ga_summary.py `
  --filter range `
  --start 2026-02-01 `
  --end 2026-02-15 `
  --export-txt reports\website_summary.txt `
  --export-csv reports\website_summary.csv `
  --export-json reports\website_summary.json
```

## Test

```powershell
python -m unittest discover -s tests -v
```

## Compile and Package (Windows)

Install build dependency:

```powershell
pip install -r requirements-build.txt
```

Build executable and release folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

This creates:

- `dist\GAParserCLI.exe`
- `dist\GAParserStart.exe` (interactive launcher wrapper)
- `release\GAParserCLI\` (exe + README + config template + quickstart)

Launcher convenience:

- Place your service account key next to `GAParserStart.exe` and rename it to `service_account.json`.
- Then run `GAParserStart.exe` without extra arguments.
- `GAParserStart.exe` auto-saves report text to `out\website_summary_YYYYMMDD_HHMMSS.txt`.
- `GAParserStart.exe` waits for `Enter` before closing so output stays visible.

Create a zip package:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\package_release.ps1
```
