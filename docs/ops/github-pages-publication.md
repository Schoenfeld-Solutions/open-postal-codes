# GitHub Pages Publication

## Triggers

The Pages workflow runs after a push to `main` or through `workflow_dispatch`.

## Flow

1. Check out the repository.
2. Set up Python `3.12`.
3. Run development gates.
4. Run `python3 -m open_postal_codes.pages --output-root out`.
5. Upload `out/` as the GitHub Pages artifact.
6. Deploy GitHub Pages.

## Permissions

The deploy job needs only `contents: read`, `pages: write`, and `id-token: write`.
