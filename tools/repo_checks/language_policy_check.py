"""Check that repository-owned text stays English-only."""

from __future__ import annotations

from pathlib import Path

from tools.repo_checks.common import fail

CHECKED_SUFFIXES = {".html", ".md", ".py", ".toml", ".yaml", ".yml"}
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "out",
}


def join_fragments(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_SNIPPETS = (
    join_fragments("aen", "derung"),
    join_fragments("aktive ", "version"),
    join_fragments("begr", "uendung"),
    join_fragments("dat", "en"),
    join_fragments("dat", "en", "aktualisierung"),
    join_fragments("dat", "en", "pflege"),
    join_fragments("dat", "ens", "aetze"),
    join_fragments("deut", "sche"),
    join_fragments("durch", "setzung"),
    join_fragments("entscheid", "ung"),
    join_fragments("entwicklungs", "checks"),
    join_fragments("fu", "er"),
    join_fragments("gefil", "terte"),
    join_fragments("geho", "eren"),
    join_fragments("her", "kunft"),
    join_fragments("hin", "weise"),
    join_fragments("initial", "isierung"),
    join_fragments("kanon", "ische"),
    join_fragments("kei", "ne ", "offenen"),
    join_fragments("konse", "quenzen"),
    join_fragments("kon", "text"),
    join_fragments("koe", "nnen"),
    join_fragments("lae", "uft"),
    join_fragments("leit", "bild"),
    join_fragments("liz", "enz"),
    join_fragments("mue", "ssen"),
    join_fragments("pla", "ene"),
    join_fragments("reg", "eln"),
    join_fragments("sicher", "heit"),
    join_fragments("statische ", "datei-api"),
    join_fragments("ur", "sprueng", "liche"),
    join_fragments("veraen", "dert"),
    join_fragments("veroeffent", "lichung"),
    join_fragments("voraus", "setzungen"),
    join_fragments("zi", "el"),
    join_fragments("zusaetz", "liche"),
)


def should_check(path: Path) -> bool:
    if path.suffix not in CHECKED_SUFFIXES:
        return False
    if any(part in IGNORED_DIRECTORIES for part in path.parts):
        return False
    return path.parts[:2] != ("data", "public")


def main() -> int:
    errors: list[str] = []

    for path in sorted(Path(".").rglob("*")):
        if not path.is_file() or not should_check(path):
            continue

        text = path.read_text(encoding="utf-8").lower()
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                errors.append(f"{path}: contains non-English repository wording")
                break

    return fail("language-policy-check", errors)


if __name__ == "__main__":
    raise SystemExit(main())
