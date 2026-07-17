# Rollback

## GitHub Pages

If a Pages deployment serves incorrect files:

1. Identify the last known-good commit on `main`.
2. Create a revert pull request for the faulty change.
3. Run the standard checks.
4. After merge, the Pages workflow runs again.

## Data

For incorrect post code data, prefer the smallest traceable correction: revert the data-refresh pull request, repair the extraction rule with tests, and rerun the refresh workflow.

If a refresh reports `reused_last_good`, investigate the named source before its 21-day budget
expires. Confirm whether the remote checksum, extraction result, expected states, and relative
deltas are plausible. Do not edit the accepted timestamp or fingerprint to extend the budget.

If the resilient refresh implementation itself behaves incorrectly:

1. Disable publication by using a manual run with `publish=false`; scheduled publication can
   also be stopped by reverting the implementation through a pull request.
2. Revert the implementation pull request and, if it introduced incorrect tracked data, the
   associated data-refresh pull request.
3. Run all standard checks against the restored baseline.
4. Repair the source contract or transaction rule with a regression test.
5. Run a complete manual refresh on `main` without fallback before restoring scheduled
   confidence.

The diagnostic JSON artifact is retained for 14 days and is the preferred incident attachment.
Do not upload raw PBFs or full generated datasets as workflow diagnostics.
