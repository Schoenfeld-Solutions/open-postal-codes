# Static File API v1

## Base Path

```text
/open-postal-codes/api/v1/
```

## Files

- `index.json`
- `at/post_code.csv`
- `at/post_code.json`
- `at/post_code.xml`
- `ch/post_code.csv`
- `ch/post_code.json`
- `ch/post_code.xml`
- `de/post_code.csv`
- `de/post_code.json`
- `de/post_code.xml`

## Manifest

`index.json` contains:

- API version
- generation timestamp
- license notice
- attribution
- per-file path, URL, gzip URL, media format, byte size, line count, record count, and SHA-256 hashes

## Gzip Files

Each public data file receives a `.gz` file in the Pages artifact. These files are not versioned under `data/public/v1/`.
