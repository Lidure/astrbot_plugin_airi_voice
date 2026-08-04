# Airi Voice Player and Page UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a persistent controllable voice preview player and improve the Plugin Pages visual design without changing the backend API.

**Architecture:** Keep audio retrieval in the existing `playVoice` flow, but route decoded audio into one shared HTML `<audio>` element. Add a dedicated player card in the page and use the existing CSS variables, responsive breakpoints, and dependency-free JavaScript/CSS.

**Tech Stack:** Static HTML, vanilla JavaScript, CSS, existing AstrBot Plugin Pages bridge, pytest, Node syntax checking.

## Global Constraints

- Do not add Python dependencies, frontend frameworks, CDN assets, or a separate server.
- Preserve the existing bridge endpoint and `audio_hex` response format.
- Preserve list, search, filter, upload, delete, reload, authorization, and error behavior.
- Use one shared audio element; never leave an older object URL or audio instance playing.
- Update plugin version and changelog after implementation.

---

### Task 1: Add the shared player markup

**Files:**
- Modify: `pages/airi-voice/index.html`
- Test: `tests/test_page_assets.py`

**Interfaces:**
- Produces DOM elements with IDs `audio-player-card`, `audio-player-title`, `audio-player-source`, and `audio-player` for `app.js`.

- [ ] **Step 1: Write the failing asset assertions**

Add assertions that the page contains an audio element with `controls` and `preload="metadata"`, plus the player card and title/source IDs.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_page_assets.py -q`

Expected: FAIL because the player markup is not present.

- [ ] **Step 3: Add the player card markup**

Insert a hidden panel after the status/error messages:

```html
<section id="audio-player-card" class="audio-player-card" hidden aria-labelledby="audio-player-title">
  <div class="audio-player-heading">
    <div>
      <p class="eyebrow">正在试听</p>
      <h2 id="audio-player-title">尚未选择语音</h2>
      <p id="audio-player-source" class="audio-player-source">选择列表中的语音开始播放</p>
    </div>
    <button id="audio-player-close" type="button" class="button button-secondary">关闭</button>
  </div>
  <audio id="audio-player" controls preload="metadata"></audio>
</section>
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run: `pytest tests/test_page_assets.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the markup**

```bash
git add pages/airi-voice/index.html tests/test_page_assets.py
git commit -m "feat: add voice preview player markup"
```

### Task 2: Replace one-off audio objects with one shared player

**Files:**
- Modify: `pages/airi-voice/app.js`
- Test: `tests/test_page_assets.py`

**Interfaces:**
- Consumes the existing `apiGet("voices/<id>/audio")` response and `audio_hex` payload.
- Produces `window.AiriVoicePage.playVoice`, `stopCurrentAudio`, and a single `HTMLAudioElement` playback lifecycle.

- [ ] **Step 1: Add static JavaScript contract assertions**

Assert that `app.js` contains `audio-player`, `URL.revokeObjectURL`, `audio.pause()`, and the close-button handler.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_page_assets.py -q`

Expected: FAIL because the current implementation creates `new Audio(url)` and has no shared player lifecycle.

- [ ] **Step 3: Implement the shared player lifecycle**

Add references to the player elements and state variables:

```js
let currentAudioUrl = null;
let currentVoice = null;
```

Implement `stopCurrentAudio({ hide = false } = {})` to pause the shared audio element, clear its source, call `load()`, revoke `currentAudioUrl`, and optionally hide the card. Update `playVoice(item)` to stop the previous playback before fetching, decode `audio_hex`, assign a new object URL to the shared element, update the title/source, unhide the card, and call `audio.play()`. Register `ended` and `error` cleanup handlers, and wire the close button plus `beforeunload` to cleanup.

- [ ] **Step 4: Run syntax and focused tests**

Run: `node --check pages/airi-voice/app.js; pytest tests/test_page_assets.py -q`

Expected: both commands exit successfully.

- [ ] **Step 5: Commit the playback behavior**

```bash
git add pages/airi-voice/app.js tests/test_page_assets.py
git commit -m "feat: add shared controllable voice playback"
```

### Task 3: Apply the visual and responsive redesign

**Files:**
- Modify: `pages/airi-voice/style.css`
- Test: `tests/test_page_assets.py`

**Interfaces:**
- Styles the new player card and existing page without changing JavaScript or backend interfaces.

- [ ] **Step 1: Add CSS contract assertions**

Assert that the stylesheet contains selectors for `.audio-player-card`, `.audio-player-heading`, `audio-player`, row hover styling, and the mobile breakpoint.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `pytest tests/test_page_assets.py -q`

Expected: FAIL because the new visual selectors do not exist.

- [ ] **Step 3: Implement the visual system**

Add a pink/blue accent gradient, layered card shadows, player spacing, audio width, status chips, row hover/focus states, and responsive rules that stack the player heading and convert row actions to a wrapped layout below 640px. Keep all colors based on the existing AstrBot CSS variables with safe fallbacks.

- [ ] **Step 4: Run the focused tests and syntax check**

Run: `pytest tests/test_page_assets.py -q; node --check pages/airi-voice/app.js`

Expected: PASS and exit code 0.

- [ ] **Step 5: Commit the visual update**

```bash
git add pages/airi-voice/style.css tests/test_page_assets.py
git commit -m "style: refresh voice management page"
```

### Task 4: Update release metadata and run full verification

**Files:**
- Modify: `metadata.yaml`, `main.py`, `README.md`, `CHANGELOG.md`

- [ ] **Step 1: Bump the version**

Set all user-facing and registration versions to `v2.9.0` and document the shared player, pause/seek controls, automatic switching, and visual refresh.

- [ ] **Step 2: Run the complete verification suite**

Run: `pytest -q; python -m py_compile main.py web_api.py voice_catalog.py request_parser.py; node --check pages/airi-voice/app.js; git diff --check`

Expected: all tests pass, compilation succeeds, JavaScript syntax check succeeds, and `git diff --check` reports no errors.

- [ ] **Step 3: Inspect the final diff and working tree**

Run: `git diff --stat; git status --short; rg -n '2\.9\.0|audio-player|stopCurrentAudio|URL\.revokeObjectURL' metadata.yaml main.py README.md CHANGELOG.md pages tests`

Expected: only intended files are changed, the player contract is present, and the working tree is clean after commit.

- [ ] **Step 4: Commit release metadata**

```bash
git add metadata.yaml main.py README.md CHANGELOG.md
git commit -m "release: improve voice player page ui"
```
