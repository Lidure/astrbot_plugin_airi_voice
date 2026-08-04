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
    assert '<section id="audio-player-card" class="audio-player-card" hidden aria-labelledby="audio-player-title">' in page
    assert '<audio id="audio-player" controls preload="metadata"></audio>' in page
    assert 'id="audio-player-title"' in page
    assert 'id="audio-player-source"' in page
    assert (page_root / "style.css").is_file()
    assert (page_root / "app.js").is_file()
