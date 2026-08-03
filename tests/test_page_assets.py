from pathlib import Path


def test_page_assets_exist_and_reference_each_other():
    """Catch a missing Plugin Page entry point or disconnected static asset."""
    page_root = Path("pages/airi-voice")
    page = (page_root / "index.html").read_text(encoding="utf-8")

    assert 'href="style.css"' in page
    assert 'src="app.js"' in page
    assert "Airi Voice" in page
    assert (page_root / "style.css").is_file()
    assert (page_root / "app.js").is_file()
