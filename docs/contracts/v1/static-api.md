# Static File API v1

## Base Path

```text
/open-postal-codes/api/v1/
```

## Files

- `index.json`
- `de/osm/streets.csv`
- `de/osm/streets.raw.csv`
- `de/osm/streets.ignore.csv`
- `li/communes.csv`

## Manifest

`index.json` contains:

- API version
- generation timestamp
- license notice
- attribution
- per-file path, URL, gzip URL, media format, byte size, line count, record count, and SHA-256 hashes

## Gzip Files

Each CSV file receives a `.gz` file in the Pages artifact. These files are not versioned under `data/public/v1/`.
