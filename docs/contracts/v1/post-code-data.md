# Post Code Data Contract v1

## Germany: Post Code Records

Files:

- `data/public/v1/de/post_code.csv`
- `data/public/v1/de/post_code.json`
- `data/public/v1/de/post_code.xml`

CSV header:

```text
code,city,country,county,time_zone
```

Record fields:

- `code`: five-digit German post code.
- `city`: city or place label associated with the post code.
- `country`: ISO 3166-1 alpha-2 country code, always `DE`.
- `county`: German county name when spatial enrichment can determine it, otherwise empty.
- `time_zone`: always `W. Europe Standard Time`.

## Format Rules

- JSON uses `{ "title": "post_code", "records": [...] }`.
- XML uses a `post_code` root element with `record` children.
- CSV, JSON, and XML contain the same deduplicated record set.
- Records are sorted by `code`, `city`, `country`, `county`, and `time_zone`.

## Compatibility

Header, field-name, title, or XML-root changes are breaking changes and require a new contract version or an explicit ADR.
