# Open Postal Codes

Open Postal Codes publishes versioned CSV files with postal-code and locality data. The repository is maintained as a Python-first data and publication project: Python code lives under `src/open_postal_codes/`, published data lives under `data/public/v1/`, and GitHub Pages serves the static file API.

## Datasets

- `data/public/v1/de/osm/streets.raw.csv`: raw German street export from OpenStreetMap data.
- `data/public/v1/de/osm/streets.ignore.csv`: manually curated exclusion list for incorrect or unusable street rows.
- `data/public/v1/de/osm/streets.csv`: filtered German street dataset for publication.
- `data/public/v1/li/communes.csv`: Liechtenstein commune reference data.

The German CSV files use this header:

```text
Name,PostalCode,Locality,RegionalKey,Borough,Suburb
```

The Liechtenstein CSV file uses this header:

```text
Key,Name,ElectoralDistrict
```

## Static File API

GitHub Pages publishes the data at stable paths:

- `/open-postal-codes/api/v1/index.json`
- `/open-postal-codes/api/v1/de/osm/streets.csv`
- `/open-postal-codes/api/v1/de/osm/streets.raw.csv`
- `/open-postal-codes/api/v1/de/osm/streets.ignore.csv`
- `/open-postal-codes/api/v1/li/communes.csv`

The Pages artifact also creates `.gz` files and metadata with hashes, file sizes, and line counts. These generated downloads are not versioned in the repository.

## Installation and Development

Requirements:

- Python `3.12` or newer
- `git`
- optional `pre-commit` for local hooks

```bash
python3 -m pip install -e '.[dev]'
pre-commit install
pre-commit install --hook-type pre-push
```

Standard checks:

```bash
python3 -m pytest --cov=open_postal_codes --cov-fail-under=85
python3 -m ruff check .
python3 -m ruff format --check .
python3 -m mypy src tests tools
python3 -m tools.repo_checks.all_checks
```

Package the Pages site locally:

```bash
python3 -m open_postal_codes.pages --output-root out
```

## Data Maintenance

This initialization does not change the existing extraction algorithm behavior. The previous filtering logic is now available as a testable Python module under `src/open_postal_codes/csv_filter.py`.

Regenerate the filtered German street data locally:

```bash
python3 -m open_postal_codes.csv_filter \
  data/public/v1/de/osm/streets.raw.csv \
  data/public/v1/de/osm/streets.ignore.csv \
  data/public/v1/de/osm/streets.csv
```

A full new OpenStreetMap extraction is not part of this initialization. It will be implemented only after a separate dependency and runtime decision.

## Attribution and License

The data work is based on OpenStreetMap data and the original OpenPLZ API Data work by Frank Stueber. This continuation is maintained by Schoenfeld Solutions.

The database remains under the ODC Open Database License (ODbL). The full license text is available in [LICENSE](LICENSE). Additional attribution notes are available in [NOTICE.md](NOTICE.md).
