from pathlib import Path


def test_page_assets_exist_and_reference_each_other():
    """Catch a missing Plugin Page entry point or disconnected static asset."""
    page = Path("pages/index.html").read_text(encoding="utf-8")

    assert 'href="style.css"' in page
    assert 'src="app.js"' in page
    assert "Airi Voice" in page
    assert Path("pages/style.css").is_file()
    assert Path("pages/app.js").is_file()
