import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from voice_catalog import CatalogError, MAX_UPLOAD_BYTES, VoiceCatalog


EXPECTED_LIMIT = 50 * 1024 * 1024


def make_catalog(tmp_path):
    return VoiceCatalog(tmp_path / "voices", tmp_path / "data", ())


def test_upload_limit_is_50_mb_for_shared_catalog_paths():
    assert MAX_UPLOAD_BYTES == EXPECTED_LIMIT


def test_web_upload_rejects_just_over_50_mb(tmp_path):
    catalog = make_catalog(tmp_path)
    with pytest.raises(CatalogError) as error:
        catalog.save_upload("too-large.mp3", "TooLargeWeb", b"x" * (EXPECTED_LIMIT + 1))
    assert error.value.code == "too_large"
    assert "50 MB" in error.value.message


def test_voice_add_upload_rejects_just_over_50_mb(tmp_path):
    catalog = make_catalog(tmp_path)
    with pytest.raises(CatalogError) as error:
        catalog.save_user_upload("too-large.ogg", "TooLargeVoiceAdd", b"x" * (EXPECTED_LIMIT + 1))
    assert error.value.code == "too_large"
    assert "50 MB" in error.value.message


def test_release_version_is_v2_10_2():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "version: v2.10.2" in metadata
    assert '"2.10.2"' in main
