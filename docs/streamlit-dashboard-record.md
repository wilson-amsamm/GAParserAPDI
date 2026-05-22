# Streamlit Dashboard Record

## Purpose

This project started as a GA4 command-line reporter. It now includes a Streamlit dashboard layer so website analytics and social-media snapshots can be viewed in one place with a more operator-friendly layout.

## What Changed

- Preserved the existing GA4 reporting engine in `src/ga_reporter`.
- Added `streamlit_app.py` as the new dashboard entrypoint.
- Added `src/ga_reporter/dashboard_data.py` to bridge the existing GA summary logic into dashboard-friendly rows.
- Added `src/ga_reporter/credentials.py` to resolve service-account credentials from backend-safe locations.
- Added `src/ga_reporter/meta_client.py` for live Meta Graph API insights loading.
- Added `src/ga_reporter/meta_capture.py` for Playwright-based Meta Business Suite metric capture.
- The capture workflow is being shifted toward export-file downloads so backend records can reference saved raw artifacts in addition to parsed metrics.
- Added `config/social_profiles.example.json` as a config-driven source for social platform snapshots such as Meta Business Suite page insights.
- Added `config/meta_accounts.example.json` for live Facebook Page and Instagram Business account mappings.
- Added `config/meta_capture_targets.example.json` for browser-automation capture targets.
- Kept the CLI scripts intact so the team can continue using the original command-line workflow when needed.

## Dashboard Scope

The first dashboard version supports:

- GA4 website metrics from the existing property config.
- Social profile snapshots from JSON config.
- Live Meta insights via backend token configuration.
- Browser-automated Meta Business Suite captures through a persistent logged-in browser profile.
- Capture targets can specify `daily`, `weekly`, or `yearly` presets so the automation normalizes the requested range before reading metrics.
- Executive KPI cards for websites and social audience.
- Website comparison charts and tabular views.
- A social metrics matrix for multiple platforms in one screen.
- An implementation record tab inside the dashboard.

## Why Meta Is Hybrid

Social APIs vary by token type, app review, permission scope, and account setup. The dashboard now supports a hybrid approach: live Meta Graph API fetches where backend credentials are available, Playwright-based browser capture where official API access is blocked, plus stable JSON snapshots for platforms or accounts that are not yet wired to a live connector.

That means the dashboard can already display:

- Meta page follower totals
- reach
- engaged users
- post impressions
- Instagram business metrics
- LinkedIn or other platform snapshots

without coupling the UI to a single provider integration.

## Architecture Notes

`streamlit_app.py`

- Handles layout, sidebar filters, status messaging, and tab rendering.

`src/ga_reporter/dashboard_data.py`

- Loads social snapshot config.
- Reuses GA summary generation from the existing reporter.
- Transforms GA and social results into dashboard tables and KPI-ready structures.

`src/ga_reporter/meta_client.py`

- Calls the Meta Graph API for configured Page or Instagram Business accounts.
- Aggregates daily values into dashboard-ready metrics.
- Returns a normalized structure that is merged into the social dashboard view.

`src/ga_reporter/meta_capture.py`

- Parses visible metric labels from Meta Business Suite pages.
- Stores captured results in backend JSON.
- Converts captured records into the same normalized dashboard structure used by other social sources.

Existing GA modules

- Still own config parsing, date resolution, GA4 API access, summary math, and export formatting.

Credential resolution

- Checks `GOOGLE_APPLICATION_CREDENTIALS` first.
- Then checks `.streamlit/secrets.toml` for either a file path or the full service-account payload.
- Then falls back to an ignored local service-account JSON in the repo root.
- The dashboard no longer needs the operator to paste the credential path into the UI.

## Current Limitations

- Meta metrics still depend on the permissions and metric availability of the connected app and token.
- Browser capture depends on a persistent logged-in Meta session and may need selector or label updates if Meta changes the page wording.
- The GA baseline logic still compares against the fixed calendar year 2025, inherited from the original CLI behavior.
- There is not yet a persistence layer or scheduled ingestion process.
- Secrets are resolved locally for now; production deployment should move them into a proper secret manager or deployment secret store.

## Recommended Next Steps

1. Add a dedicated connectors layer for live providers such as Meta Graph API, Google Search Console, and other social platforms.
2. Introduce a normalized metric taxonomy so cross-platform KPIs can be compared more consistently.
3. Store historical snapshots in a small local database or warehouse so the Streamlit app can chart trends over time.
4. Add authentication and secrets management for production deployment.
5. Expand the dashboard into more focused tabs for acquisition, social engagement, and executive summaries.
