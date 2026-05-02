# Consumer Smoke Checks for v1

These checks help consumers verify the local or published static API without changing the public contract.

## Expected Files

The v1 manifest lists these files:

- `at/post_code.csv`
- `at/post_code.json`
- `at/post_code.xml`
- `ch/post_code.csv`
- `ch/post_code.json`
- `ch/post_code.xml`
- `de/post_code.csv`
- `de/post_code.json`
- `de/post_code.xml`

Each file also has a `.gz` variant in the Pages artifact.

## Local Artifact Smoke

Package the site locally:

```bash
python3 -m open_postal_codes.pages --output-root out
```

Verify the manifest, hashes, gzip files, and record counts with only the Python standard library:

```bash
python3 - <<'PY'
import gzip
import hashlib
import json
from pathlib import Path

root = Path("out/api/v1")
manifest = json.loads((root / "index.json").read_text(encoding="utf-8"))
assert manifest["base_path"] == "/open-postal-codes/api/v1/"
assert len(manifest["files"]) == 9

for entry in manifest["files"]:
    path = root / entry["path"]
    gzip_path = root / f"{entry['path']}.gz"
    data = path.read_bytes()
    gzip_data = gzip_path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    assert hashlib.sha256(gzip_data).hexdigest() == entry["gzip_sha256"]
    assert gzip.decompress(gzip_data) == data
    if path.suffix == ".csv":
        assert entry["records"] == max(data.count(b"\n") - 1, 0)

print("v1 artifact smoke passed")
PY
```

## Published API Smoke

Set the published base URL and inspect the manifest:

```bash
BASE="https://schoenfeld-solutions.github.io/open-postal-codes/api/v1"
python3 -m json.tool < <(curl -fsS "${BASE}/index.json")
```

Download one file per country and verify the sentinel rows:

```bash
BASE="https://schoenfeld-solutions.github.io/open-postal-codes/api/v1"
curl -fsS "${BASE}/de/post_code.csv" | grep '^28195,Bremen,DE,'
curl -fsS "${BASE}/at/post_code.csv" | grep '^1010,Wien,AT,'
curl -fsS "${BASE}/ch/post_code.csv" | grep '^8001,Zürich,CH,'
```

Consumers should prefer the manifest hashes when caching or mirroring files. The record counts are collapse guards, not a promise that future refreshes will preserve exact row totals.

## Contract Expectations

- `country` is one of `DE`, `AT`, or `CH`.
- `code` uses five digits for Germany and four digits for Austria and Switzerland.
- `state` is the first-level administrative subdivision: Bundesland for Germany and Austria, canton for Switzerland.
- `county` can be empty when no lower administrative area is available.
- `time_zone` is `W. Europe Standard Time` for all D-A-CH records.
