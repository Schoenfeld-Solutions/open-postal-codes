# Data Refresh

## Scheduled Refresh

The `Refresh D-A-CH Post Code Data` workflow runs on a schedule and by manual dispatch. It downloads D-A-CH PBF files from Geofabrik into runner-local temporary storage, extracts and validates candidate source CSV outputs, rebuilds public CSV/JSON/XML files, and opens or updates a pull request when tracked files change. When required pull request checks pass, the workflow squash-merges the exact checked data commit and verifies the merge and branch deletion.

Scheduled runs publish only from `refs/heads/main`. A manual dispatch is validation-only by default. Set its boolean `publish` input to `true` and select `main` explicitly to permit branch, pull request, and merge writes. A manual run from any other ref remains validation-only even when `publish` is requested.

The refresh command emits flushed per-source progress logs during metadata checks, skipped-source detection, downloads, extraction, record counting, fallback decisions, failures, and public output rebuilds. These logs are maintainer observability only; they are not a stable public interface.

Every workflow run writes a machine-readable JSON report with per-source status, duration, checksum, metrics, deltas, observed states, inferred record count, warnings, and a safe error class. Source statuses are `fresh`, `unchanged`, `reused_last_good`, or `failed`. The final Actions summary and JSON artifact are produced even when an earlier step fails. The artifact expires after 14 days and never contains PBF files or complete generated datasets.

When a candidate is rejected and a last-known-good source is reused, the accepted source metrics remain at the top level while the rejected candidate's fingerprint, metrics, deltas, states, and inference count are preserved under `candidate` for diagnosis.

The extraction step also recalculates location-primary markers, ranks, and evidence metadata for every public row, so committed regional CSV files must use the same schema as the public export.

The Pages manifest publishes two timestamps:

- `generated_at`: when the Pages artifact was packaged.
- `data_refreshed_at`: when every D-A-CH source last completed without fallback. Scoped runs and runs that reuse a last-known-good source do not advance it.

## Manual Scoped Run

```bash
python3 -m open_postal_codes.refresh_data \
  --download-root /tmp/open-postal-codes-pbf \
  --countries de \
  --regions bremen \
  --report-path /tmp/open-postal-codes-refresh-report.json
```

Refresh only Austria and Switzerland:

```bash
python3 -m open_postal_codes.refresh_data \
  --download-root /tmp/open-postal-codes-pbf \
  --countries at,ch
```

## Local Business Central Export

The unofficial Business Central workbook is generated only on a maintainer workstation. It reads the public v1 CSV files, keeps only `is_primary_location=true` rows, maps the v1 `state` field into the Business Central `Bundesregion` column, and writes ignored files under `tmp/private-outputs/export/`.

```bash
python3 -m open_postal_codes.business_central --repository-root .
```

Default paths:

- Template: `tmp/private-outputs/input/PLZ.xlsx`
- Workbook: `tmp/private-outputs/export/PLZ_BusinessCentral_DACH.xlsx`
- Guardrails: `tmp/private-outputs/export/PLZ_BusinessCentral_DACH_Guardrails.md`

These files are local artifacts. They are not committed, not uploaded by Pages, and not part of the public static API contract.

## Rules

- Raw `.osm.pbf` files are never committed.
- Normalized CSV outputs under `data/regional/v1/<country>/post_code/` are committed through refresh pull requests.
- `data/sources/geofabrik-regions.json` stores accepted remote fingerprints, verification timestamps, record and unique-post-code metrics, and accepted record state codes. Existing metadata remains readable; raw observed boundary codes remain run diagnostics.
- Before large downloads, the refresh inventories all selected sources. An unreachable source without a valid committed baseline stops the run before extraction.
- Timeouts, connection failures, and HTTP 408, 429, 500, 502, 503, and 504 responses use at most three attempts. `Retry-After` is honored up to 60 seconds; otherwise retries use bounded backoff. Semantic extraction and quality failures are not retried.
- Candidate regional and country outputs are validated before atomic replacement. A hard failure must not leave partial tracked changes.
- A known network, integrity, extraction, or quality failure may reuse a validated committed regional CSV for at most 21 days. The accepted fingerprint and verification timestamp do not advance, so the next run retries the source. Missing, invalid, or older baselines fail the workflow.
- A run with an in-budget last-known-good source may publish other validated updates, but the source is marked `reused_last_good` in the report and pull request. Unknown programming failures are never hidden by fallback.
- Source gates require known non-empty states, the configured state set, and bounded movement from the accepted source baseline. Country gates require all 16 German states, nine Austrian states, or 26 Swiss cantons together with absolute and relative collapse limits.
- A source rejects record loss above 15%, unique-post-code loss above 12%, or growth above 25%. A country rejects record loss above 10%, unique-post-code loss above 5%, or growth above 20%.
- The Austrian emergency floor is 2,700 records and 2,000 unique post codes. It is not sufficient on its own; complete state coverage and relative deltas remain mandatory.
- Warning bands report material movement before a hard threshold is crossed.
- A refresh with no tracked diff is a successful no-op.
- Code-only unit, Ruff, formatting, and Mypy checks run before PBF downloads. Data, repository, Pages-package, and diff gates run after candidate generation.
- Runs are serialized without cancellation, use `ubuntu-24.04`, and stop after 120 minutes. The workflow does not cache PBFs or use a source matrix.
- Required pull request checks stop after 20 minutes. A timeout or failure leaves the pull request open and includes PR diagnostics in the log and summary.

## Token Permissions

The normal pull request gates run with read-only repository permissions. The data-refresh workflow also keeps its default workflow token read-only. Validation-only runs use that token only for checkout. Publication-enabled checkout, data branch publication, pull request creation, required check inspection, and merge use a dedicated GitHub App installation token.

Required repository configuration:

- Variable: `DATA_REFRESH_APP_CLIENT_ID`
- Secret: `DATA_REFRESH_APP_PRIVATE_KEY`

The installed App needs only repository metadata, contents write, pull requests write, and checks read permissions. It must not need administration, Pages, secrets, or workflow permissions.

The workflow leaves the pull request open if required checks fail or exceed 20 minutes. Merge uses squash mode, deletes `dev/data-refresh-post-code`, is pinned to the exact checked head commit, and verifies the final merged state before the workflow succeeds.
