# Data and Security Guardrails

## Principle

This repository publishes open data. Even so, secrets, private tokens, and unapproved local data must not enter code, tests, docs, workflows, or artifacts.

## Rules

- Do not store secrets in files or logs.
- Do not version local download dumps.
- Error output should describe structural problems without printing unnecessary data volume.
- Generated artifacts such as `out/`, coverage reports, and local logs remain unversioned.
- New production dependencies require documented rationale, tests, and approval.
