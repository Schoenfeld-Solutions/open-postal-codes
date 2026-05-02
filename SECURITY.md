# Security Policy

## Supported Scope

This repository publishes open postal code data and the tooling used to refresh and package it. Security work focuses on keeping secrets, private files, raw downloads, and unsafe automation out of the public repository.

## Reporting

Please report sensitive issues privately to the repository owner instead of opening a public issue. Include the affected path, workflow, or command and the smallest useful reproduction details.

## Handling Rules

- Do not commit credentials, tokens, private workbook templates, raw PBF downloads, logs, or local exports.
- Treat workflow permissions as least-privilege settings.
- Keep public data changes reproducible through the documented refresh process.
- Prefer small fixes with tests and a clear rollback path.
