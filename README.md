# GAParser

Config-driven analytics workspace for GA4 reporting and a Streamlit dashboard for website plus social summaries.

## What it does

- Loads website-to-property mappings from `config/properties.json`
- Pulls `activeUsers` and `organicGoogleSearchImpressions` by default
- Keeps impressions strictly on `organicGoogleSearchImpressions` (no `screenPageViews` fallback)
- Aggregates impressions using the `landingPagePlusQueryString` breakdown to align with GA4 Search Console traffic reports
- Prints a formatted CLI summary
- Optionally exports to `txt`, `csv`, and `json`
- Provides a Streamlit dashboard for GA4 websites and social platform snapshots
- Includes a config-driven social profile format for Meta Business Suite style page insights and other channels

## Project layout

- `src/ga_reporter/` application code
- `config/` property config files
- `docs/` implementation records
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

## Configure social snapshots

1. Copy `config/social_profiles.example.json` to `config/social_profiles.json`
2. Fill in the latest metrics from Meta Business Suite, Instagram, LinkedIn, or other platforms you want on the dashboard

## Configure live Meta insights

1. Copy `config/meta_accounts.example.json` to `config/meta_accounts.json`
2. Fill in your Facebook Page IDs and Instagram Business account IDs
3. Add `meta_access_token` to `.streamlit/secrets.toml` or set `META_ACCESS_TOKEN`

The dashboard will pull live Meta insights for configured accounts and merge them with any manual social snapshots.

## Configure automated Meta Business Suite capture

If the official Meta app/token path is blocked, you can capture the visible Business Suite metrics with a persistent logged-in browser profile.
If the UI allows export, the script now also downloads the export files into backend storage.

1. Copy `config/meta_capture_targets.example.json` to `config/meta_capture_targets.json`
2. Fill in each `insights_url`
3. Set each target `period_preset` to `daily`, `weekly`, or `yearly`
3. Install Playwright browser binaries:

```powershell
python -m playwright install chromium
```

4. Run the capture job:

```powershell
python .\scripts\capture_meta_business_suite.py --pause-on-login
```

The first run opens a persistent browser profile, lets you complete login, captures the visible metrics, and saves them to `data/meta_business_suite_records.json` for the dashboard.
Export downloads are saved under `data/meta_business_suite_exports/`.

You can also override the preset for all targets in one run:

```powershell
python .\scripts\capture_meta_business_suite.py --date-preset weekly
```

## Schedule the daily Meta social sync

On this Windows host, use Task Scheduler as the cron equivalent.

1. Make sure the dedicated Playwright profile in `.playwright/meta-business-suite-profile` is already logged in to Meta Business Suite.
2. Register the daily task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register_meta_daily_sync_task.ps1
```

This creates the task `OnlinePlatformAnalytics_MetaDailySync` and schedules it daily at `06:15`.

The task runs:

```powershell
python .\scripts\run_meta_daily_sync.py
```

The wrapper forces the Meta capture into the `daily`/`Yesterday` window, writes logs under `logs/meta_daily_sync/`, and upserts daily social rows into PostgreSQL when backend DB config is available.

## Capture TikTok Shop analytics

1. Review `config/tiktok_targets.json`
2. Start the capture with the dedicated persistent profile
3. Log in to TikTok Seller Center if needed, confirm the correct shop/date window is visible, then continue

```powershell
python .\scripts\capture_tiktok_shop.py --pause-on-login
```

Optional session-health check:

```powershell
python .\scripts\check_tiktok_session.py
```

Helpful hardening flags:
- `--use-system-profile` to reuse the browser's real Edge/Chrome profile
- `--profile-backup-dir <path>` to save known-good Playwright profile snapshots after successful captures
- `expected_markers` in `config/tiktok_targets.json` to assert the intended shop/region is visible before capture

Captured records are saved to:
- `data/tiktok_shop_records.json`

If PostgreSQL is configured, the same capture also upserts daily TikTok rows for:
- gross revenue
- items sold
- page views
- visitors
- conversion rate

## Configure the Viber bot

The project now supports a lightweight Viber bot backend for:

- receiving Viber webhook callbacks
- storing subscribed users in PostgreSQL
- sending the latest website + social summary to subscribed users

Add a Viber section to `.streamlit/secrets.toml`:

```toml
[viber]
auth_token = "your-viber-bot-auth-token"
webhook_url = "https://your-public-domain.example.com/webhook"
bot_name = "OPA Bot"
avatar_url = ""
welcome_message = "Online Platform Analytics bot is connected. You can now receive dashboard summary updates here."
host = "0.0.0.0"
port = 8787
```

Run the webhook receiver:

```powershell
python .\scripts\run_viber_bot.py
```

Register the webhook with Viber:

```powershell
python .\scripts\set_viber_webhook.py
```

Send the latest warehouse summary to all subscribed users:

```powershell
python .\scripts\send_viber_summary.py
```

The Viber bot stores subscribers in PostgreSQL once they subscribe or send a message through the bot webhook.

## Authentication

Use one of:

- `--service-account path\to\service_account.json`
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable
- `.streamlit/secrets.toml` for the dashboard backend

Also add the service account email to each GA4 property with at least Viewer access.

### Streamlit backend secret storage

For the dashboard, prefer backend-only configuration instead of entering secrets in the UI.

1. Create `.streamlit/secrets.toml`
2. Add either a file path or the full JSON payload

Path-based example:

```toml
google_service_account_path = "C:\\Users\\Administrator\\DevProjs\\OnlinePlatformAnalytics\\service_account.json"
```

Embedded JSON example:

```toml
[google_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
universe_domain = "googleapis.com"
```

The dashboard automatically resolves credentials from Streamlit secrets, `GOOGLE_APPLICATION_CREDENTIALS`, or a local ignored service-account file.

## Run

### Streamlit dashboard

```powershell
streamlit run .\streamlit_app.py
```

Default dashboard URL on this host:

- `http://quadro-analytics.local:8508`
- `http://192.168.2.166:8508`

For other Windows client machines on the LAN, you can add the hostname with:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\add_dashboard_host_alias.ps1
```

Run that from an elevated PowerShell window on the client machine, or copy the script there first and then run it.

If you prefer a `.bat` launcher, use:

```bat
.\scripts\add_dashboard_host_alias.bat
```

The dashboard lets you:

- pick a date range for GA4
- load website metrics from the GA config
- resolve GA credentials from backend-only storage
- load live Meta Page and Instagram Business insights from backend-only credentials
- load Playwright-captured Meta Business Suite metrics from backend storage
- display social platform metrics from `config/social_profiles.json`
- review the implementation record directly in the UI

### CLI

Custom range:

```powershell
python ga_summary.py --filter range --start 2026-02-01 --end 2026-02-15
```

Preset filters:

```powershell
python ga_summary.py --filter daily
python ga_summary.py --filter weekly
python ga_summary.py --filter yearly
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

## Documentation

- Dashboard implementation record: `docs/streamlit-dashboard-record.md`

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
