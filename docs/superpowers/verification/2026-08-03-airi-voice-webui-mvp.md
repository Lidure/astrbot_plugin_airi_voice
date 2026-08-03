# Airi Voice WebUI MVP verification handoff

Date: 2026-08-03

## Implementation

- Release target: v2.8.0
- Branch: `feature/airi-voice-webui-mvp`
- Implemented commit range: `d10add3..a77498de4fe1668ec6f42f24cb15456021fbe600`, with follow-up verification fixes through the current branch tip
- Target AstrBot version: **PENDING** (no AstrBot runtime is available in this workspace)

## Automated verification

| Check | Result | Evidence |
| --- | --- | --- |
| Python compilation | PASS | `python -m py_compile main.py web_api.py voice_catalog.py request_parser.py` exited 0. |
| Configuration JSON | PASS | `python -c "import json; json.load(open('_conf_schema.json', encoding='utf-8'))"` exited 0. |
| Full automated test suite | PASS | `pytest -q`: 46 passed in 0.54s. |
| Whitespace errors | PASS | `git diff --check` exited 0. |

## Fixtures available in this environment

- No live AstrBot installation or Dashboard session.
- No Plugin Pages bridge.
- No browser session for console, dark-mode, or responsive-layout inspection.
- No verified audio fixtures for manual playback, upload, or oversize testing.

## Manual Dashboard checklist (Plugin Pages-capable AstrBot)

All cases below are **PENDING**. They require a Plugin Pages-capable AstrBot, an authenticated Dashboard session, and suitable audio fixtures.

| Case | Status | Manual procedure |
| --- | --- | --- |
| Page discovery and load | PENDING | Reload the plugin, open its Dashboard Plugin Page, and confirm Airi Voice appears and loads without browser-console errors. |
| List, search, and source filter | PENDING | Confirm the initial list; search a known keyword; filter `builtin`, `user_added`, and `extra_voices`; confirm totals and rows update. |
| Audio preview | PENDING | Preview an existing playable item and confirm the controlled audio URL plays the intended file. |
| Upload, filename-derived keyword | PENDING | Upload one allowed `.wav`, `.mp3`, `.ogg`, `.silk`, `.amr`, `.flac`, or `.m4a` file without changing the suggested keyword; confirm it appears under `extra_voices`. |
| Upload, edited keyword | PENDING | Upload an allowed fixture with an edited safe keyword; confirm that exact keyword is listed. |
| Plugin Pages bridge upload route | PENDING | In the live Plugin Pages page, verify the upload uses `bridge.upload("voices/upload/<encoded-keyword>", file)` and reaches the keyword-bearing upload route successfully. |
| Duplicate keyword rejection | PENDING | Attempt to upload a file with an effective keyword already present; confirm a stable validation error and no new file. |
| Unsafe, invalid, and oversized rejection | PENDING | Attempt an unsafe keyword (empty, slash, backslash, `..`, or control character), a disallowed extension, and a file over 20 MB; confirm rejection without persistence. |
| Deletion confirmation | PENDING | Delete a `user_added` or `extra_voices` item; cancel once, then confirm once; verify the list and file state reflect each choice. |
| Builtin deletion rejection | PENDING | Attempt deletion of a `builtin` item and confirm it remains unavailable as a destructive action. |
| Reload | PENDING | Add or remove an eligible fixture out of band if applicable, use Reload, and confirm the count/list update. |
| Permission denial | PENDING | Use an authenticated non-admin account for upload, deletion, and reload; confirm each mutation is denied while read-only listing remains available. |
| Dark mode | PENDING | Switch the Dashboard theme and confirm text, controls, rows, errors, and disabled states remain legible. |
| Narrow layout | PENDING | Test below 640 px width and confirm row actions stack without clipping or horizontal overflow. |
| Missing-file, empty, and error states | PENDING | Configure or simulate a missing item, an empty catalog, and a failed network request; confirm each state is visible and understandable. |

## Older AstrBot fallback checklist

All cases below are **PENDING**. Run these on an AstrBot version without Plugin Pages support and record the actual version above.

| Case | Status | Manual procedure |
| --- | --- | --- |
| Plugin load | PENDING | Reload the plugin and confirm compatibility fallback does not prevent it from loading. |
| `/voice.help` and `/voice.list` | PENDING | Run both commands and confirm expected help/list output. |
| Ordinary keyword | PENDING | Send a configured ordinary keyword and confirm direct voice triggering. |
| Random matrix | PENDING | Confirm direct random voice, single-slash random filter when enabled, and rejection of double-slash random filter. |
| Existing admin commands | PENDING | As an administrator, exercise the existing add, delete, and reload commands with safe fixtures. |

## Limitations and release decision

This environment has no live AstrBot Dashboard/Plugin Pages bridge and no browser verification. No AstrBot, browser, playback, upload, authorization, or responsive-layout result is claimed here. Manual verification must complete with recorded fixtures and an actual AstrBot version before release.

The local `v2.8.0` tag and any release publication are intentionally deferred while these manual cases remain pending. No tag, push, or remote publication was performed.
