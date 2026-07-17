# PLANS-008: Resilient D-A-CH data refresh

This plan follows `docs/plans/PLANS.md`.

## Purpose / Big Picture

Make the scheduled D-A-CH refresh resilient to incomplete Geofabrik administrative
relations without allowing silent state loss or unbounded stale data. A source candidate
must be validated before it replaces tracked data, temporary upstream failures may reuse a
validated last-known-good source for at most 21 days, and every run must explain its outcome.

## Progress

- [x] Add source-aware state contracts and German primary-state recovery.
- [x] Add source and country quality gates with backward-compatible metadata baselines.
- [x] Make refresh promotion transactional and add bounded last-known-good fallback.
- [x] Add bounded network retries and a machine-readable refresh report.
- [x] Reorganize the scheduled workflow for early code checks and always-on diagnostics.
- [x] Repair Brandenburg and verify the Sachsen-Anhalt regression snapshot.
- [x] Update operations documentation, the changelog, and the architecture decision record.
- [x] Run the complete local validation and pre-merge PBF replay sequence.
- [ ] Run one complete manual refresh on merged `main` and observe the next Monday schedule.
- [ ] Update and immutably pin GitHub Actions in a separate pull request.

## Surprises & Discoveries

- The failed run completed all 18 downloads and extractions before rejecting 252 German rows
  without a state and an Austrian record count below the old static floor.
- The Sachsen-Anhalt state relation could not be assembled because one relation way was
  outside the regional extract boundary.
- The committed Brandenburg regional output contains only Berlin records, which country-wide
  record floors did not detect.
- Austrian total records declined gradually while unique post-code coverage remained stable,
  so a single total-record threshold is not a reliable collapse detector.

## Decision Log

- Keep regional German PBF sources instead of moving immediately to a full-Germany extract.
- Assign an otherwise unclassified German candidate only to the configured primary state of
  its source; never apply this inference to Austria, Switzerland, foreign-tagged candidates,
  or candidates outside the reconstructed source coverage.
- Require Berlin geometry in the Brandenburg source and Bremen geometry in the Niedersachsen
  source before primary-state inference is allowed.
- Validate candidates in memory and promote outputs only after all selected sources and
  rebuilt countries pass hard gates.
- Reuse only a structurally valid last-known-good regional output whose last successful
  verification is no more than 21 days old.
- Keep public v1 paths and record schemas unchanged.
- Treat `actions/setup-node` as out of scope because this repository has no Node toolchain.
- Update actual Action dependencies and immutable pins in a separate pull request.

## Outcomes & Retrospective

The implementation and initial data repair are complete on `dev/resilient-data-refresh` and
remain subject to manual pull request review. The repair produced 9,454 German records, 8,168
unique post codes, all 16 states, and no empty state values. Brandenburg now has 463 records
and 393 unique post codes across `DE-BB` and embedded `DE-BE`; 273 records use guarded primary
state recovery. Current Sachsen-Anhalt has 252 records and 186 unique post codes, all 252 with
guarded recovery.

The downloaded regression snapshot from 2026-07-12 was verified against MD5
`2a5753054c26ea60550556a4575a1512` and replayed with exactly 252 records, 252 inferred state
assignments, and zero empty states. The current Brandenburg and Sachsen-Anhalt PBFs were also
replayed with the final candidate-tag guards; the persisted regional files match those final
results.

Pre-merge evidence on 2026-07-17:

- `python -m pytest --cov=open_postal_codes --cov-fail-under=90`: 188 passed, 92.75% coverage
- `python -m mypy src tests tools`: passed
- `python -m ruff check .` and `python -m ruff format --check .`: passed
- `python -m tools.repo_checks.all_checks`: every repository gate passed
- `python -m open_postal_codes.pages --output-root <temporary-directory>`: packaged 9 API files
- `git diff --check`: passed

The plan remains open for the deliberately manual review of the initial repair, the first
complete post-merge `main` refresh without fallback, the following Monday soak run, and the
separate immutable Action-pin pull request. No threshold was tuned to the observed Austrian
record count: the accepted 2,700/2,000 emergency floors remain combined with complete state
coverage and stricter relative source and country deltas.

## Context and Orientation

Primary implementation areas:

- `src/open_postal_codes/countries.py` and `src/open_postal_codes/osm_extract.py` define source
  contracts and spatial enrichment.
- `src/open_postal_codes/refresh_quality.py` owns pure source/country validation.
- `src/open_postal_codes/refresh_data.py` owns remote I/O, orchestration, fallback, reporting,
  and atomic promotion.
- `.github/workflows/data-refresh.yml` runs the scheduled refresh and guarded publication.
- `tools/repo_checks/public_data_quality_check.py` reuses the same quality contracts against
  committed data.

The implementation must preserve the accepted low-cost, regional-source, GitHub App, and
exact-head merge decisions in ADRs 0005, 0007, 0012, and 0013.
