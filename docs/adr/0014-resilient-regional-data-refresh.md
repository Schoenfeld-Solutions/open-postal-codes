# ADR 0014: Make regional data refreshes resilient

- Date: 2026-07-16
- Status: Accepted
- Decision owner: Gabriel
- Impacts: OSM extraction, data quality, source metadata, GitHub Actions, operations

## Status

Accepted.

## Context

The scheduled D-A-CH refresh on 2026-07-13 downloaded and processed every configured
Geofabrik source, but the generated data failed the repository gates. The Sachsen-Anhalt
regional PBF contained an incomplete state relation, so 252 otherwise valid rows had no
state. Austria also fell below a fixed 3,000-record floor even though its unique post-code
inventory remained plausible. A separate review found that the committed Brandenburg
regional output contained only Berlin rows, which country-level totals did not detect.

Regional extracts are intentionally retained because they keep runner time, memory, and
upstream bandwidth below the cost of the full Germany PBF. They can, however, clip or omit
individual boundary members. A robust refresh must therefore validate each source before it
changes tracked data, distinguish expected regional topology from extraction collapse, and
remain operable during a bounded upstream defect.

## Decision

The refresh will use an explicit source contract and a transactional, last-known-good update
model.

### Source-aware state recovery

- Every state has a canonical ISO 3166-2 code and display name.
- Each German regional source declares its primary state. Brandenburg additionally requires
  Berlin, and Niedersachsen additionally requires Bremen as embedded state geometries.
- Austria requires all nine states and Switzerland all 26 cantons. Neither country permits
  primary-state inference.
- Source coverage is the union of same-country country, state, and county geometries present
  in the PBF. Existing state assignments always take precedence.
- Only otherwise unassigned candidates inside a German regional source may inherit that
  source's primary state. Multi-state sources permit inference only when their embedded state
  geometry is present. Foreign, outside-coverage, and unknown-state candidates are never
  inferred.

### Transaction and bounded fallback

- The refresh inventories all selected sources before large downloads. A source that is
  unavailable and has no valid committed baseline stops the run before extraction.
- Transient network and server failures use at most three attempts with bounded backoff.
  Semantic extraction and quality failures are not retried.
- Candidate source and country outputs are validated before atomic replacement of tracked
  files and accepted metadata.
- A known network, integrity, extraction, or quality failure may reuse a previously validated
  regional CSV for at most 21 days. Its accepted fingerprint and verification timestamps do
  not advance, so the next run retries the source. Unknown programming failures and expired
  or invalid baselines fail hard.
- A hard failure leaves tracked data unchanged. A run with an in-budget fallback may publish
  other validated updates and makes the reused source visible in its report and pull request.
- The global source `generated_at` advances only after a complete D-A-CH run without fallback.

### Layered quality gates

Quality is enforced per source and per country. Source gates require known, non-empty states,
the configured state set, a non-empty primary state, and bounded changes from the accepted
baseline. Country gates require exactly 16 German states, nine Austrian states, and 26 Swiss
cantons together with absolute collapse floors and relative record and unique-post-code
deltas. Warning bands surface material movement before a hard threshold is reached.

This replaces reliance on a single total-record floor. The Austrian emergency floor is 2,700
records and 2,000 unique post codes, but relative deltas and complete state coverage remain
mandatory. Source loss limits are 15% for records and 12% for unique post codes, with 25%
maximum growth. Country loss limits are 10% and 5%, respectively, with 20% maximum growth.

### Workflow behavior

- Code-only unit, lint, format, and type checks run before PBF downloads. Generated-data,
  repository, Pages-package, and diff checks run after extraction.
- Scheduled runs may publish only from `refs/heads/main`. Manual runs default to validation
  only and require the explicit `publish` input on `main` before any branch or pull request is
  written.
- Refresh runs are serialized without cancellation on `ubuntu-24.04` and have a 120-minute
  timeout. No PBF cache or source matrix is introduced.
- The CLI writes a machine-readable JSON report. A concise summary and the report artifact
  are retained for 14 days even when an earlier step fails; PBF and generated data files are
  never uploaded as diagnostics.
- Required pull request checks are bounded to 20 minutes. Exact-head checks before merge and
  merge-state checks afterwards keep automated publication traceable.

## Rationale

The source contract repairs the observed class of clipped state relations without inventing
geography outside a known regional coverage area. Per-source validation catches defects such
as the missing Brandenburg output before country totals can conceal them. A 21-day fallback
allows two normal weekly recovery opportunities plus operational margin while preventing
indefinite silent staleness. Transactional writes ensure a failed attempt cannot partially
replace a known-good release.

## Consequences

- Source metadata grows backward-compatibly to retain accepted metrics, state coverage,
  fingerprints, and verification timestamps.
- Maintainers must investigate any fallback warning before its 21-day budget expires.
- A scheduled run can succeed with a clearly reported, in-budget last-known-good source; it
  fails once that source expires or no valid baseline exists.
- Diagnostics become useful without retaining large or licensed raw PBF artifacts in Actions.
- The public v1 paths and CSV, JSON, and XML schemas do not change.

## Alternatives considered

- **Lower only the Austrian record floor:** rejected because it would not detect state loss or
  a future relative collapse.
- **Fail the whole refresh for every regional defect:** rejected because it prevents unrelated
  validated sources from advancing during a bounded upstream incident.
- **Download the full Germany PBF:** deferred because its bandwidth, storage, and runtime cost
  is disproportionate to the observed failure.
- **Use an OSM API or a new boundary service:** rejected to avoid another availability,
  authentication, and rate-limit dependency.
- **Parallelize or cache regional PBFs:** deferred until measurements show the added upstream
  load and merge complexity are justified.

## Enforcement

- Unit tests cover source contracts, inference boundaries, deltas, fallback expiry, retries,
  reports, and atomic update behavior.
- Repository checks enforce country and source quality invariants.
- Workflow policy checks enforce ordering, publication gates, diagnostics, timeout, runner,
  and the absence of PBF matrices and caches.

## Rollout

Merge the implementation through a normal pull request. Review the initial Brandenburg and
Sachsen-Anhalt repair manually, then run one complete manual refresh on `main` without
fallback. The following scheduled Monday run is the soak test. Roll back by reverting the
implementation pull request and, when necessary, the most recent data pull request.
