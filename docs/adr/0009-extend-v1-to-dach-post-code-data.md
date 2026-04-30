# ADR 0009: Extend v1 to D-A-CH post code data

- Date: 2026-04-30
- Status: Accepted
- Decision owner: Gabriel
- Impacts: public v1 contract, data refresh, extraction configuration

## Status

Accepted.

## Context

The v1 post code contract is stable enough to support Austria and Switzerland without changing the public field set. The existing Germany extraction logic already defines the right ranking and evidence model, but country code, post code length, Geofabrik sources, and administrative boundary enrichment must be configurable.

## Decision

The repository extends v1 additively with `at/post_code.*` and `ch/post_code.*` files next to the existing `de/post_code.*` files. Country configuration controls ISO code, post code validation, time zone, Geofabrik source files, and administrative levels used for spatial enrichment.

## Rationale

Adding paths inside v1 keeps existing Germany consumers stable while making the new D-A-CH files discoverable in the same manifest. A shared country configuration avoids duplicating extraction rules and makes future country additions explicit.

## Consequences

- The Pages manifest publishes nine post code data files.
- Germany keeps regional Geofabrik source files; Austria and Switzerland use full-country Geofabrik PBF files.
- Pull request CI remains download-free; large PBF downloads still run only in the refresh workflow or in approved local refresh runs.
- Empty country files are valid only as initial contract placeholders until a refresh pull request populates the country data.

## Enforcement

- `open_postal_codes.countries` is the source of country and Geofabrik configuration.
- `open_postal_codes.post_code` validates post codes and time zones through the country configuration.
- `open_postal_codes.osm_extract` uses the selected country configuration for OSM filtering and enrichment.
- Repository checks validate all D-A-CH public paths and post code invariants.

## Rollout

The implementation adds country-scoped output roots, updates the refresh workflow, commits schema-valid `AT` and `CH` public placeholders, and allows the refresh workflow to populate Austria and Switzerland from Geofabrik PBF files.
