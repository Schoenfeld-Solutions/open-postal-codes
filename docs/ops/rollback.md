# Rollback

## GitHub Pages

If a Pages deployment serves incorrect files:

1. Identify the last known-good commit on `main`.
2. Create a revert pull request for the faulty change.
3. Run the standard checks.
4. After merge, the Pages workflow runs again.

## Data

For incorrect post code data, prefer the smallest traceable correction: revert the data-refresh pull request, repair the extraction rule with tests, and rerun the refresh workflow.
