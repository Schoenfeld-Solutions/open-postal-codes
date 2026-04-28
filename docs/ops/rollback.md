# Rollback

## GitHub Pages

If a Pages deployment serves incorrect files:

1. Identify the last known-good commit on `main`.
2. Create a revert pull request for the faulty change.
3. Run the standard checks.
4. After merge, the Pages workflow runs again.

## Data

For incorrect CSV data, prefer the smallest traceable correction: a row in `streets.ignore.csv`, a corrected CSV file, or a revert of the data refresh.
