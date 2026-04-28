# Data Refresh

## Regenerate the Filtered Street File

```bash
python3 -m open_postal_codes.csv_filter \
  data/public/v1/de/osm/streets.raw.csv \
  data/public/v1/de/osm/streets.ignore.csv \
  data/public/v1/de/osm/streets.csv
```

## Rules

- `streets.ignore.csv` is intentionally maintained manually.
- Headers must not change without a contract decision.
- A full OpenStreetMap extraction is a separate workstream.
- Run the standard checks after every data refresh.
