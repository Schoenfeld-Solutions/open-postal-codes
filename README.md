# Open Postal Codes

Open Postal Codes publishes a Germany-only static file API for post code records. The repository is maintained as a Python-first data and publication project: extraction and packaging code lives under `src/open_postal_codes/`, published data lives under `data/public/v1/`, and GitHub Pages serves the static file API.

## Datasets

- `data/public/v1/de/post_code.csv`: German post code records as CSV.
- `data/public/v1/de/post_code.json`: German post code records as JSON.
- `data/public/v1/de/post_code.xml`: German post code records as XML.

The CSV file uses this header:

```text
code,city,country,county,time_zone
```

JSON uses the title `post_code` and a `records` array. XML uses a `post_code` root element with `record` children.

## Static File API

GitHub Pages publishes the data at stable paths:

- `/open-postal-codes/api/v1/index.json`
- `/open-postal-codes/api/v1/de/post_code.csv`
- `/open-postal-codes/api/v1/de/post_code.json`
- `/open-postal-codes/api/v1/de/post_code.xml`

The Pages artifact also creates `.gz` files and metadata with hashes, file sizes, media types, and record counts. Generated downloads are not versioned in the repository.

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

The scheduled data-refresh workflow downloads regional Germany PBF files from Geofabrik into runner-local temporary storage, extracts post code records with Python, rebuilds public CSV/JSON/XML files, and opens a pull request only when tracked files change.

Manual scoped smoke run:

```bash
python3 -m open_postal_codes.refresh_data \
  --download-root /tmp/open-postal-codes-pbf \
  --regions bremen
```

Raw PBF files are never committed. Regional normalized CSV outputs under `data/regional/v1/de/post_code/` are committed only by refresh pull requests.

## Attribution and License

The data work is based on OpenStreetMap data, regional extracts provided by Geofabrik GmbH, and the original OpenPLZ API Data work by Frank Stueber. This continuation is maintained by Schoenfeld Solutions.

The database remains under the ODC Open Database License (ODbL). The full license text is available in [LICENSE](LICENSE). Additional attribution notes are available in [NOTICE.md](NOTICE.md).
