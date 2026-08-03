# Airi Voice WebUI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AstrBot Dashboard page for browsing, searching, previewing, uploading, deleting, and reloading Airi Voice audio while preserving existing chat commands and older AstrBot fallback behavior.

**Architecture:** Keep the current file-based voice storage and runtime `voice_map`, but move scanning, validation, listing, upload, deletion, and reload operations into `voice_catalog.py`. Add a thin `web_api.py` compatibility adapter for the exact Plugin Pages API supported by the running AstrBot version, plus a dependency-free static page under `pages/`. Existing `main.py` handlers call the catalog instead of duplicating filesystem logic.

**Tech Stack:** Python 3.10+, AstrBot Plugin Pages/Web API, vanilla HTML/CSS/JavaScript, pytest, existing Pillow/aiohttp dependencies.

## Global Constraints

- Do not add a database or a separate web server.
- Preserve `voices/`, `user_added/`, and `extra_voices/` directory compatibility.
- Preserve direct normal-keyword triggering, direct `随机语音`, `/随机关键词`, and rejection of `//随机关键词`.
- Only user-added and web-uploaded files may be deleted from the web page; bundled `voices/` files are read-only.
- Accept only `.mp3`, `.wav`, `.ogg`, `.silk`, and `.amr`, with a 20 MB upload limit.
- Reject empty keywords, `/`, `\\`, `..`, and control characters.
- Upload, delete, and reload require the existing plugin administrator check.
- Plugin Pages registration failure must not prevent the plugin from loading.
- Do not require a new AstrBot minimum version; older versions retain chat commands and config-page behavior.
- The MVP release target is `v2.8.0`; bug fixes after release use `v2.8.1`.

---

### Task 1: Lock the AstrBot Plugin Pages API and add a compatibility smoke test

**Files:**
- Create: `tests/test_web_api_compatibility.py`
- Create: `web_api.py`
- Modify: `main.py:611-715`
- Inspect: official AstrBot Plugin Pages documentation and the installed AstrBot runtime source

**Interfaces:**
- `RegistrationResult` dataclass: `pages_registered: bool` and `api_registered: bool`.
- Produces `register_web_features(context, plugin) -> RegistrationResult` in `web_api.py`.
- `RegistrationResult.pages_registered` and `RegistrationResult.api_registered` are booleans.
- Registration catches unavailable API symbols and returns a disabled result instead of raising.

- [ ] **Step 1: Inspect the actual runtime API**

Run from the AstrBot runtime environment:

```powershell
rg -n "Plugin Pages|registered_web_apis|register_web|pages/" "$env:ASTRBOT_HOME" -S
```

Record the public registration methods, callback signatures, request/response types, static-page mount convention, and Dashboard authentication behavior before writing integration code.

- [ ] **Step 2: Write the failing compatibility test**

```python
def test_registration_failure_does_not_raise():
    class BrokenContext:
        def __getattr__(self, name):
            raise AttributeError(name)

    from web_api import register_web_features
    result = register_web_features(BrokenContext(), object())
    assert result.pages_registered is False
    assert result.api_registered is False
```

- [ ] **Step 3: Run the test to verify failure**

Run: `pytest tests/test_web_api_compatibility.py::test_registration_failure_does_not_raise -q`

Expected: FAIL because `web_api.py` and `register_web_features` do not exist.

- [ ] **Step 4: Implement the compatibility adapter**

Implement `register_web_features(context, plugin)` to detect the public API discovered in Step 1, register `pages/` and routes when available, catch `ImportError`, `AttributeError`, and registration exceptions, log one warning, and return `RegistrationResult(False, False)` on fallback.

- [ ] **Step 5: Call registration from plugin initialization**

Call `register_web_features(self.context, self)` after directory and catalog initialization. Store the result on `self.web_features`. Do not alter normal message-handler registration.

- [ ] **Step 6: Verify and commit**

Run:

```powershell
python -m py_compile main.py web_api.py
pytest tests/test_web_api_compatibility.py -q
```

Then commit:

```powershell
git add tests/test_web_api_compatibility.py web_api.py main.py
git commit -m "feat: add compatible webui registration adapter"
```

### Task 2: Extract and test the file-based voice catalog

**Files:**
- Create: `voice_catalog.py`
- Create: `request_parser.py`
- Create: `tests/test_voice_catalog.py`
- Modify: `main.py:678-715, 980-1045, 1544-1630`

**Interfaces:**
- `VoiceEntry` dataclass: `id`, `name`, `source`, `path`, `extension`, `size`, `available`.
- `ParsedRequest` dataclass: `kind` and optional `keyword`; supported kinds are `keyword`, `random_all`, `random_filter`, `admin_command`, and `ignore`.
- `VoiceCatalog.list_entries(query: str = "", source: str | None = None) -> list[VoiceEntry]`.
- `VoiceCatalog.refresh() -> dict[str, str]`.
- `VoiceCatalog.validate_keyword(keyword: str) -> str`.
- `VoiceCatalog.save_upload(filename: str, keyword: str, data: bytes) -> VoiceEntry`.
- `VoiceCatalog.delete(entry_id: str) -> None`.
- `VoiceCatalog.resolve_entry(entry_id: str) -> VoiceEntry`.
- `VoiceCatalog.audio_path(entry_id: str) -> Path`.
- `parse_request(text: str, enable_prefix: bool, trigger_mode: str, raw_text: str | None = None) -> ParsedRequest`.

- [ ] **Step 1: Write failing validation tests**

```python
import pytest
from voice_catalog import VoiceCatalog, CatalogError

def test_rejects_unsafe_keywords(tmp_path):
    catalog = VoiceCatalog(tmp_path / "voices", tmp_path / "data")
    for value in ("", "/x", "\\x", "..", "a\nname"):
        with pytest.raises(CatalogError):
            catalog.validate_keyword(value)

def test_audio_path_cannot_escape_allowed_roots(tmp_path):
    catalog = VoiceCatalog(tmp_path / "voices", tmp_path / "data")
    with pytest.raises(CatalogError):
        catalog.audio_path("../../secret")
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run: `pytest tests/test_voice_catalog.py -q`

Expected: FAIL because the module and methods do not exist.

- [ ] **Step 3: Implement catalog construction and validation**

Store resolved roots for `voices`, `user_added`, and `extra_voices`. Define the five allowed extensions, `MAX_UPLOAD_BYTES = 20 * 1024 * 1024`, stable IDs in the form `<source>:<relative filename>`, and `CatalogError(code, message)`.

- [ ] **Step 4: Implement scanning and listing**

Scan all three roots, preserve current precedence for `voice_map`, mark missing configured files unavailable, return deterministic keyword sorting, implement case-insensitive substring search, and accept only `builtin`, `user_added`, or `extra_voices` source filters.

- [ ] **Step 5: Add scan/list tests**

Create temporary roots containing one file in each source, assert search returns the matching keyword, source filtering returns only the requested source, and missing files are marked unavailable.

- [ ] **Step 6: Implement mutations**

Save uploads only under `extra_voices`, normalize a validated extension, reject duplicate effective keywords across all sources, generate IDs only from controlled relative paths, and permit deletion only for `user_added` and `extra_voices`. `audio_path` resolves an ID through the index rather than treating input as a path.

- [ ] **Step 7: Add mutation tests**

Cover successful upload, invalid extension, 20 MB boundary, duplicate rejection, user-file deletion, builtin deletion rejection, missing-entry errors, and refresh after mutation. Use byte fixtures; do not require valid audio decoding.

- [ ] **Step 8: Integrate runtime state**

Replace duplicated scanning/mutation logic in `main.py` with catalog calls while keeping `self.voice_map` and `self.sorted_keys` synchronized. Compare complete `extra_voice_pool` content instead of only its length. Preserve `/voice.add`, `/voice.delete`, `/voice.reload`, ordinary keywords, and random behavior.

- [ ] **Step 9: Verify and commit**

Run: `pytest tests/test_voice_catalog.py -q`

Then commit:

```powershell
git add voice_catalog.py tests/test_voice_catalog.py main.py
git commit -m "refactor: extract safe voice catalog management"
```

### Task 3: Implement authenticated backend routes

**Files:**
- Modify: `web_api.py`
- Create: `tests/test_web_api_routes.py`
- Modify: `main.py` only for a public helper needed by route callbacks

**Interfaces:**
- `GET /voices`: query `q`, `source`; returns `{"items": [VoiceEntry JSON objects], "total": n}`.
- `GET /voices/{id}/audio`: returns a framework audio/file response.
- `POST /voices/upload`: accepts multipart file data and keyword.
- `DELETE /voices/{id}`: calls `VoiceCatalog.delete` after admin check.
- `POST /voices/reload`: refreshes catalog after admin check.

- [ ] **Step 1: Write route authorization and response tests**

Use fake request/context objects matching the API signatures discovered in Task 1. Assert mutation calls return 403 without admin permission, list responses contain `items` and `total`, and catalog errors map to stable 400/404 JSON responses.

- [ ] **Step 2: Run route tests to verify failure**

Run: `pytest tests/test_web_api_routes.py -q`

Expected: FAIL because callbacks are not implemented.

- [ ] **Step 3: Implement list and audio callbacks**

Return only public metadata. For audio, use the framework response type discovered in Task 1 and never return an absolute path in JSON.

- [ ] **Step 4: Implement upload, delete, and reload callbacks**

Validate request fields before calling the catalog. Convert `CatalogError` to the declared JSON error shape. Reuse the plugin’s existing `_check_admin(event)`.

- [ ] **Step 5: Verify and commit**

Run: `pytest tests/test_web_api_routes.py -q`

Then commit:

```powershell
git add web_api.py tests/test_web_api_routes.py main.py
git commit -m "feat: add voice management web routes"
```

### Task 4: Build the static Plugin Page

**Files:**
- Create: `pages/airi-voice/index.html`
- Create: `pages/airi-voice/app.js`
- Create: `pages/airi-voice/style.css`
- Create: `tests/test_page_assets.py`

**Interfaces:**
- The page calls the five backend endpoints with relative URLs supplied by the Plugin Pages bridge.
- `app.js` maintains `state = { items, query, source, loading, error }`.
- `app.js` exposes `loadVoices`, `uploadVoice`, `deleteVoice`, `reloadVoices`, and `playVoice`.

- [ ] **Step 1: Write the asset smoke test**

```python
from pathlib import Path

def test_page_assets_exist_and_reference_each_other():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    assert 'src="app.js"' in page
    assert 'href="style.css"' in page
    assert "Airi Voice" in page
```

- [ ] **Step 2: Run the test to verify failure**

Run: `pytest tests/test_page_assets.py -q`

Expected: FAIL because `pages/` does not exist.

- [ ] **Step 3: Implement semantic page structure**

Add accessible headings, summary cards, search input, source select, refresh button, upload form, list/table, empty state, error area, and delete confirmation. Do not embed absolute API URLs.

- [ ] **Step 4: Implement page behavior**

Use `fetch` with JSON error parsing, `FormData` for upload, disabled buttons during mutations, refresh after success, HTML-escaped rendering for server keywords, and controlled audio preview URLs.

- [ ] **Step 5: Implement responsive styling**

Use CSS variables compatible with light/dark themes. Make the list usable below 640px by stacking row actions. Keep Chinese labels beginner-friendly.

- [ ] **Step 6: Verify and commit**

Run: `pytest tests/test_page_assets.py -q`

Then commit:

```powershell
git add pages tests/test_page_assets.py
git commit -m "feat: add airi voice dashboard page"
```

### Task 5: Update configuration, documentation, and version metadata

**Files:**
- Modify: `_conf_schema.json`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `metadata.yaml`
- Modify: `main.py` register version and help text

- [ ] **Step 1: Document WebUI capability and fallback**

Explain that the page appears only on AstrBot versions supporting Plugin Pages and that older versions retain commands and config-page management. Do not add a required page-enable switch.

- [ ] **Step 2: Add a beginner quick start**

Document Dashboard navigation, search, preview, upload, delete, reload, allowed formats, 20 MB limit, permissions, fallback commands, and this exact trigger matrix:

```text
普通关键词       -> 直接触发
随机语音         -> 直接触发
/随机关键词      -> 前缀开启时触发
//随机关键词     -> 不触发
```

- [ ] **Step 3: Add the v2.8.0 changelog and bump versions**

Update `metadata.yaml`, the register version, README badge, and CHANGELOG. Include the compatibility fallback and security restrictions. Do not claim browser verification until Task 7.

- [ ] **Step 4: Validate and commit**

Run:

```powershell
python -c "import json; json.load(open('_conf_schema.json', encoding='utf-8'))"
git diff --check
```

Then commit:

```powershell
git add _conf_schema.json README.md CHANGELOG.md metadata.yaml main.py
git commit -m "docs: document airi voice webui management"
```

### Task 6: Add automated trigger regression tests

**Files:**
- Create: `tests/test_trigger_matrix.py`
- Modify: `main.py` only if the parser needs a regression fix

**Interfaces:**
- Tests call `parse_request(text, enable_prefix, trigger_mode, raw_text=None) -> ParsedRequest`; the result has `kind` and `keyword` fields and does not require AstrBot, real audio playback, or a live Dashboard.

- [ ] **Step 1: Write concrete matrix tests**

```python
from request_parser import parse_request

def test_normal_keyword_is_direct_in_both_prefix_settings():
    assert parse_request("打卡啦摩托", False, "direct").kind == "keyword"
    assert parse_request("打卡啦摩托", True, "direct").kind == "keyword"

def test_random_voice_is_direct_exception_when_enabled():
    result = parse_request("随机语音", True, "direct")
    assert result.kind == "random_all"

def test_random_filter_requires_single_slash_when_enabled():
    result = parse_request("随机猫", True, "direct")
    assert result.kind == "ignore"
    result = parse_request("随机猫", True, "direct", raw_text="/随机猫")
    assert result.kind == "random_filter"
    assert result.keyword == "猫"

def test_double_slash_is_rejected():
    assert parse_request("/随机猫", True, "direct", raw_text="//随机猫").kind == "ignore"

def test_legacy_hashvoice_mode_is_preserved():
    result = parse_request("#voice 打卡啦摩托", False, "prefix")
    assert result.kind == "keyword"
    assert result.keyword == "打卡啦摩托"
```

- [ ] **Step 2: Run and fix only parser behavior**

Run: `pytest tests/test_trigger_matrix.py -q`. Keep changes limited to `request_parser.py` and its `main.py` integration so WebUI work does not alter unrelated LLM or admin behavior.

- [ ] **Step 3: Run the full automated suite**

Run: `pytest -q`. Expected: all available tests pass. Dashboard and missing-file checks remain in the manual checklist.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_trigger_matrix.py main.py
git commit -m "test: protect trigger behavior during webui work"
```

### Task 7: Manual Dashboard verification and release handoff

**Files:**
- Create: `docs/superpowers/verification/2026-08-03-airi-voice-webui-mvp.md`
- Modify: `CHANGELOG.md` only if manual verification finds a user-visible correction

- [ ] **Step 1: Run static checks**

```powershell
python -m py_compile main.py web_api.py voice_catalog.py
python -c "import json; json.load(open('_conf_schema.json', encoding='utf-8'))"
git diff --check
```

- [ ] **Step 2: Reload the plugin in AstrBot Dashboard**

On a Plugin Pages-capable AstrBot, open the Airi Voice page and record whether it loads without console errors. On an older AstrBot, confirm the plugin loads and `/voice.help`, `/voice.list`, ordinary keywords, and existing admin commands work.

- [ ] **Step 3: Manually test page operations**

Using available audio files, verify list, search, source filter, preview, upload with filename-derived keyword, upload with edited keyword, duplicate rejection, deletion confirmation, builtin deletion rejection, and reload count update.

- [ ] **Step 4: Manually test security and UI states**

Verify non-admin mutation denial, invalid extension, oversized file, unsafe keyword, missing-file display, empty state, network error, dark mode, and narrow-screen layout. If a fixture is unavailable, record it as untested rather than passing it.

- [ ] **Step 5: Record results**

Write the actual AstrBot version, available fixtures, passed cases, failed cases, and known limitations into the verification document.

- [ ] **Step 6: Prepare the v2.8.0 release**

Only after automated checks and manual verification pass:

```powershell
git status --short
git log -8 --oneline
git tag v2.8.0
git show v2.8.0 --stat
```

Do not push or publish remotely without explicit user approval.
