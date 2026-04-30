# ADR 0008: Extend v1 post code ranking metadata

- Date: 2026-04-29
- Status: Accepted
- Decision owner: Gabriel
- Impacts: public v1 contract, data refresh, extraction quality

## Status

Accepted.

## Context

Post code areas can cover multiple places, and one place can appear with more than one post code in OpenStreetMap data. A place-level primary boolean is misleading for cities such as Dresden that validly have many post codes. Consumers need a deterministic primary location per post code plus ranks for sorting post codes within a place.

## Decision

The repository replaces the current v1 `post_code` schema in place with `is_primary_location`, `location_rank`, `postal_code_rank`, `source`, and `evidence_count`. `is_primary_location` is unique per `(country, code)` post code. `postal_code_rank` ranks post codes within each normalized place without claiming that one post code is an official primary code for that place.

## Rationale

The repository is still in its foundation phase, so an explicit ADR is enough for this v1 schema replacement. Keeping the current paths avoids a parallel v2 publication while adding the minimum metadata needed to sort shared post codes and multi-code places transparently.

## Consequences

- CSV, JSON, and XML outputs gain five metadata fields.
- Existing consumers of the previous v1 header must adjust.
- Secondary locations and additional post codes remain published when they have usable evidence.
- Public records expose quality metadata without adding coordinates or raw OpenStreetMap object identifiers.

## Enforcement

- `open_postal_codes.post_code` finalizes records with exactly one primary location per post code and contiguous ranks per post code and place.
- `open_postal_codes.osm_extract` attaches source and evidence metadata during extraction.
- Repository checks validate the public header, boolean encoding, rank contiguity, source enum, evidence counts, and primary-location uniqueness.

## Rollout

The next data refresh rewrites all regional and public post code files with the enriched v1 schema. The static API paths remain unchanged.
