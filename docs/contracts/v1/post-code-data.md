# Post Code Data Contract v1

## D-A-CH: Post Code Records

Files:

- `data/public/v1/de/post_code.csv`
- `data/public/v1/de/post_code.json`
- `data/public/v1/de/post_code.xml`
- `data/public/v1/at/post_code.csv`
- `data/public/v1/at/post_code.json`
- `data/public/v1/at/post_code.xml`
- `data/public/v1/ch/post_code.csv`
- `data/public/v1/ch/post_code.json`
- `data/public/v1/ch/post_code.xml`

CSV header:

```text
code,city,country,county,time_zone,is_primary_location,location_rank,postal_code_rank,source,evidence_count
```

Record fields:

- `code`: country-specific post code; `DE` uses five digits, `AT` and `CH` use four digits.
- `city`: city or place label associated with the post code.
- `country`: ISO 3166-1 alpha-2 country code, one of `DE`, `AT`, or `CH`.
- `county`: country-specific administrative area name when spatial enrichment can determine it, otherwise empty.
- `time_zone`: country-specific Windows time zone identifier; D-A-CH records use `W. Europe Standard Time`.
- `is_primary_location`: boolean marker for the highest-ranked location row within the same `(country, code)` post code.
- `location_rank`: one-based rank of this `(city, county)` row within the same `(country, code)` post code.
- `postal_code_rank`: one-based rank of this `code` within the same normalized `(country, county, city)` place.
- `source`: either `postal_boundary` or `address_fallback`.
- `evidence_count`: count of accepted OpenStreetMap address objects supporting the same `(code, city, county)` row.

## Format Rules

- JSON uses `{ "title": "post_code", "records": [...] }`.
- XML uses a `post_code` root element with `record` children.
- CSV, JSON, and XML contain the same deduplicated record set.
- CSV and XML encode `is_primary_location` as `true` or `false`; JSON encodes it as a boolean.
- JSON encodes `location_rank`, `postal_code_rank`, and `evidence_count` as integers.
- Exactly one row per `(country, code)` post code has `is_primary_location=true`.
- `is_primary_location=false` means the row is a known secondary or weaker-evidence location for that post code, not that the row is invalid.
- Places with multiple post codes use `postal_code_rank` for deterministic sorting instead of a place-level primary boolean.
- A city with many post codes can have many `is_primary_location=true` rows, one per post code.
- Records are sorted by the full public field order.

## Compatibility

ADR 0008 records the intentional in-place v1 schema extension. Future header, field-name, title, or XML-root changes remain breaking changes and require a new contract version or an explicit ADR.
