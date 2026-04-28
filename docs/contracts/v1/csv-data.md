# CSV Data Contract v1

## Germany: OSM Streets

Files:

- `data/public/v1/de/osm/streets.raw.csv`
- `data/public/v1/de/osm/streets.ignore.csv`
- `data/public/v1/de/osm/streets.csv`

Header:

```text
Name,PostalCode,Locality,RegionalKey,Borough,Suburb
```

Rules:

- `streets.raw.csv` is the unprocessed exported street dataset.
- `streets.ignore.csv` contains complete rows removed from the raw dataset.
- `streets.csv` contains the filtered dataset with the unchanged header.

## Liechtenstein: Communes

File:

- `data/public/v1/li/communes.csv`

Header:

```text
Key,Name,ElectoralDistrict
```

## Compatibility

Header changes are breaking changes and require a new contract version or an explicit ADR.
