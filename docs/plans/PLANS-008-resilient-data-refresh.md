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
- [x] Run one complete manual refresh on merged `main` without last-known-good fallback.
- [x] Update and immutably pin GitHub Actions in a separate pull request.
- [ ] Inspect the authenticated Dependabot update-job log and run `Check for updates`.
- [ ] Observe the next Monday schedule as the final soak test.

## Surprises & Discoveries

- The failed run completed all 18 downloads and extractions before rejecting 252 German rows
  without a state and an Austrian record count below the old static floor.
- The Sachsen-Anhalt state relation could not be assembled because one relation way was
  outside the regional extract boundary.
- The committed Brandenburg regional output contains only Berlin records, which country-wide
  record floors did not detect.
- Austrian total records declined gradually while unique post-code coverage remained stable,
  so a single total-record threshold is not a reliable collapse detector.
- The successful full refresh warned that `actions/upload-artifact@v4.6.2` still targets the
  deprecated Node.js 20 runtime and was being forced onto Node.js 24.

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

The implementation and initial data repair were manually reviewed and merged through pull
request 24. The repair produced 9,454 German records, 8,168 unique post codes, all 16 states,
and no empty state values. Brandenburg now has 463 records and 393 unique post codes across
`DE-BB` and embedded `DE-BE`; 273 records use guarded primary state recovery. Current
Sachsen-Anhalt has 252 records and 186 unique post codes, all 252 with guarded recovery.

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

Manual `main` run 29556211816 completed successfully after pull request 24 without
last-known-good fallback: 16 sources were fresh, two were unchanged, and none reused
last-known-good data. Its generated data pull request 25 was merged at the exact checked head.
The accepted country outputs contained 9,454 German, 2,909 Austrian, and 4,876 Swiss records,
and the Pages workflow also completed successfully.

The separate Action hygiene change pins every used third-party Action to an immutable release
commit and updates the workflow policy gate to reject floating tags. It also updates
`actions/upload-artifact` to v7.0.1 after the full-run deprecation warning. Local evidence for
that change comprises 206 passing tests with 92.75% coverage, 199 passing unit tests, Ruff,
format, Mypy, every repository check, Pages packaging, and `git diff --check`.
`actions/setup-node` remains absent because the repository has no Node toolchain. The current
Dependabot configuration is structurally valid and has no open update pull request, so it was
not changed without job-log evidence. The authenticated update-job log and manual update run,
plus the following Monday soak run, remain open. No threshold was tuned to the observed
Austrian record count: the accepted 2,700/2,000 emergency floors remain combined with complete
state coverage and stricter relative source and country deltas.

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
