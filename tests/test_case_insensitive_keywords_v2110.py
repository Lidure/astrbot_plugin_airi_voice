import json
from pathlib import Path

import pytest

from voice_catalog import CatalogError, VoiceCatalog
from request_parser import match_trigger_keyword


ROOT = Path(__file__).resolve().parents[1]


def make_catalog(tmp_path, case_insensitive=False):
    return VoiceCatalog(
        tmp_path / "voices",
        tmp_path / "data",
        (),
        case_insensitive_keywords=case_insensitive,
    )


def test_case_insensitive_config_defaults_to_false():
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    assert schema["case_insensitive_keyword_match"]["type"] == "bool"
    assert schema["case_insensitive_keyword_match"]["default"] is False


def test_catalog_allows_case_variants_when_disabled(tmp_path):
    catalog = make_catalog(tmp_path, case_insensitive=False)
    catalog.save_upload("test.wav", "test", b"a")
    catalog.save_upload("TEST.wav", "TEST", b"b")
    assert set(catalog.trigger_map()) == {"test", "TEST"}


def test_catalog_rejects_case_variants_when_enabled(tmp_path):
    catalog = make_catalog(tmp_path, case_insensitive=True)
    catalog.save_upload("test.wav", "test", b"a")
    with pytest.raises(CatalogError) as error:
        catalog.save_upload("TEST.wav", "TEST", b"b")
    assert error.value.code == "duplicate_keyword"
    assert "忽略大小写" in error.value.message
    assert "TEST" in error.value.message
    assert "test" in error.value.message


def test_alias_conflict_message_explains_case_insensitive_mode(tmp_path):
    catalog = make_catalog(tmp_path, case_insensitive=True)
    catalog.save_upload("test.wav", "test", b"a")
    entry = catalog.list_entries()[0]
    with pytest.raises(CatalogError) as error:
        catalog.add_alias(entry.id, "TEST")
    assert error.value.code == "duplicate_keyword"
    assert "忽略大小写" in error.value.message
    assert "TEST" in error.value.message


def test_runtime_keyword_matching_can_ignore_case():
    assert match_trigger_keyword("TEST", ["test"], case_insensitive=True) == "test"
    assert match_trigger_keyword("TEST", ["test"], case_insensitive=False) is None
    assert match_trigger_keyword("hello TEST world", ["test"], fuzzy_match=True, case_insensitive=True) == "test"


def test_runtime_keyword_matching_reads_plugin_config_when_option_is_omitted():
    class FakePlugin:
        config = {"case_insensitive_keyword_match": True}

        def resolve(self):
            return match_trigger_keyword("TEST", ["test"])

    assert FakePlugin().resolve() == "test"


def test_catalog_reads_plugin_config_when_option_is_omitted(tmp_path):
    class FakePlugin:
        config = {"case_insensitive_keyword_match": True}

        def build(self):
            return VoiceCatalog(tmp_path / "voices", tmp_path / "data")

    catalog = FakePlugin().build()
    catalog.save_upload("test.wav", "test", b"a")
    with pytest.raises(CatalogError):
        catalog.save_upload("TEST.wav", "TEST", b"b")


def test_webui_error_patch_extracts_chinese_backend_message():
    patch = (ROOT / "pages" / "airi-voice" / "error_patch.js").read_text(encoding="utf-8")
    assert "error.response.data" in patch
    assert "payload.error.message" in patch
    assert "Request failed with status code" not in patch


def test_webui_message_parser_reads_rejected_bridge_response_directly():
    app = (ROOT / "pages" / "airi-voice" / "app.js").read_text(encoding="utf-8")
    assert "error.response.data" in app
    assert "JSON.parse" in app
    assert "后端未返回可读的错误详情" in app
