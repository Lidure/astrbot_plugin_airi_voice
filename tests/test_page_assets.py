from pathlib import Path


def test_page_assets_exist_and_reference_each_other():
    """Catch a missing Plugin Page entry point or disconnected static asset."""
    page_root = Path("pages/airi-voice")
    page = (page_root / "index.html").read_text(encoding="utf-8")

    assert 'href="style.css"' in page
    assert 'src="app.js"' in page
    assert "Airi Voice" in page
    assert 'accept=".wav,.mp3,.ogg,.silk,.amr,.flac,.m4a,audio/*"' in page
    assert ".silk" in page and ".amr" in page
    assert '<section id="audio-player-card" class="audio-player-card is-mini" hidden aria-labelledby="audio-player-title">' in page
    assert '<audio id="audio-player" controls preload="metadata"></audio>' in page
    assert 'id="audio-player-title"' in page
    assert 'id="audio-player-source"' in page
    assert '<p id="audio-player-source" class="audio-player-source">选择列表中的语音开始播放</p>' in page
    assert (page_root / "style.css").is_file()
    assert (page_root / "app.js").is_file()


def test_voice_preview_uses_the_shared_player_cleanup_contract():
    """Catch previews that bypass the page player or leak their Blob URLs."""
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert 'document.getElementById("audio-player")' in script
    assert "URL.revokeObjectURL" in script
    assert "audio.pause()" in script
    assert 'elements.audio.addEventListener("error", () => stopCurrentAudio({ hide: true }))' in script


def test_voice_preview_ignores_stale_requests_and_exposes_stop_interface():
    """Catch an older preview response replacing the current shared player."""
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert "let previewRequestVersion = 0" in script
    assert "const requestVersion = ++previewRequestVersion" in script
    assert script.count("if (!isCurrentPreviewRequest(requestVersion)) return;") >= 4
    assert "function stopCurrentAudio" in script
    assert "playVoice, stopCurrentAudio" in script


def test_voice_page_styles_define_player_and_responsive_contracts():
    """Keep the player and voice-row visual affordances in the page stylesheet."""
    styles = Path("pages/airi-voice/style.css").read_text(encoding="utf-8")

    assert ".audio-player-card" in styles
    assert ".audio-player-heading" in styles
    assert "#audio-player" in styles
    assert "tbody tr:hover" in styles
    assert "@media (max-width: 640px)" in styles


def test_voice_page_supports_fixed_feedback_and_bridge_compatible_delete():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")
    styles = Path("pages/airi-voice/style.css").read_text(encoding="utf-8")

    assert 'id="error-message"' in page
    assert 'id="upload-form"' in page
    assert 'bridge().apiPost(`voices/${encodeURIComponent(voiceId)}/delete`)' in script
    assert "apiDelete" not in script
    assert "position: fixed" in styles
    assert ".upload-fields" in styles


def test_voice_page_has_compact_player_toggle_and_upload_card_contract():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")
    styles = Path("pages/airi-voice/style.css").read_text(encoding="utf-8")

    assert 'id="audio-player-toggle"' in page
    assert 'id="audio-player-mini-play"' in page
    assert 'id="audio-player-close"' not in page
    assert 'class="upload-actions"' in page
    assert "is-mini" in script
    assert ".audio-player-card.is-mini" in styles
    assert ".audio-player-card.is-mini #audio-player" in styles
    assert ".audio-player-card.is-mini .audio-player-actions" in styles
    assert "grid-template-columns: repeat(2" in styles
    assert "is-expanded" not in script
    assert 'elements.audio.addEventListener("ended", () => stopCurrentAudio' not in script
    assert "if (elements.audio.ended) elements.audio.currentTime = 0;" in script
    assert ".upload-actions" in styles
