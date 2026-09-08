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
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert schema["case_insensitive_keyword_match"]["type"] == "bool"
    assert schema["case_insensitive_keyword_match"]["default"] is False
    assert 'self.case_insensitive_keyword_match = bool(self.config.get("case_insensitive_keyword_match", False))' in main


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


def test_main_wires_case_insensitive_matching_to_runtime_and_catalog():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "case_insensitive_keywords=self.case_insensitive_keyword_match" in main
    assert "match_trigger_keyword(request.keyword or \"\", self.voice_map.keys(), self.fuzzy_keyword_match, self.case_insensitive_keyword_match)" in main


def test_webui_error_handling_reads_axios_response_message():
    app = (ROOT / "pages" / "airi-voice" / "app.js").read_text(encoding="utf-8")
    assert "error.response" in app
    assert "error.response.data" in app
    assert "messageFrom(error" in app
    assert "Request failed with status code" not in app
