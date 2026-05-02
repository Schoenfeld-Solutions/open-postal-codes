## Summary

- 

## Validation

- [ ] `python3 -m pytest --cov=open_postal_codes --cov-fail-under=90`
- [ ] `python3 -m ruff check .`
- [ ] `python3 -m ruff format --check .`
- [ ] `python3 -m mypy src tests tools`
- [ ] `python3 -m tools.repo_checks.all_checks`
- [ ] `python3 -m open_postal_codes.pages --output-root out`
- [ ] `git diff --check`

## Risk and Rollback

- Risk:
- Rollback:
