# Task 2 report — safe voice catalog extraction

## Status

Completed and committed as `refactor: extract safe voice catalog management`.

## Changed files

- `voice_catalog.py` — resolved-root catalog, controlled IDs, validation, scanning, upload and deletion operations.
- `request_parser.py` — request classification that preserves direct keyword and random-prefix handling.
- `main.py` — catalog-backed runtime synchronization, full `extra_voice_pool` comparison, and catalog-backed voice management commands.
- `tests/test_voice_catalog.py` — catalog safety, scan/list, mutation, refresh, and parser-contract tests.

## Verification

```text
pytest tests/test_voice_catalog.py -q
9 passed in 0.21s

python -m py_compile main.py voice_catalog.py request_parser.py
exit 0

git diff --check
exit 0
```

## Concern

The Task 2 brief explicitly restricts catalog files to `.wav`, `.mp3`, `.ogg`, `.flac`, and `.m4a`. This is narrower than the older plan and historical helper allowlist, which mention `.silk` and `.amr`; catalog-managed `/voice.add` rejects those two formats to follow the brief exactly.

## Reviewer follow-up: duplicate effective keywords

`VoiceCatalog.refresh()` now rejects case-insensitive keyword collisions across every catalog source with `CatalogError("duplicate_keyword", ...)`. This prevents the old source-order overwrite from choosing a voice for ambiguous names. Tests cover builtin/user-added, builtin/extra, and user-added/extra collisions. Trigger parsing and handler semantics were not changed.
