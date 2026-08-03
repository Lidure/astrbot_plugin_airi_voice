import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_catalog import CatalogError, MAX_UPLOAD_BYTES, VoiceCatalog


def make_catalog(tmp_path, extra_voice_pool=()):
    return VoiceCatalog(tmp_path / "voices", tmp_path / "data", extra_voice_pool)


def test_rejects_unsafe_keywords(tmp_path):
    catalog = make_catalog(tmp_path)

    for value in ("", "/x", "\\x", "..", "a\nname"):
        with pytest.raises(CatalogError, match="keyword"):
            catalog.validate_keyword(value)


def test_audio_path_cannot_escape_allowed_roots(tmp_path):
    catalog = make_catalog(tmp_path)

    with pytest.raises(CatalogError) as error:
        catalog.audio_path("../../secret")
    assert error.value.code == "not_found"


def test_lists_entries_with_search_source_filter_and_missing_configured_file(tmp_path):
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "Builtin.wav").write_bytes(b"builtin")
    (tmp_path / "data" / "user_added").mkdir(parents=True)
    (tmp_path / "data" / "user_added" / "User.ogg").write_bytes(b"user")
    (tmp_path / "data" / "extra_voices").mkdir()
    (tmp_path / "data" / "extra_voices" / "Extra.flac").write_bytes(b"extra")
    catalog = make_catalog(tmp_path, ["extra_voices/missing.mp3"])

    entries = catalog.list_entries()

    assert [(entry.name, entry.source, entry.available) for entry in entries] == [
        ("Builtin", "builtin", True),
        ("Extra", "extra_voices", True),
        ("missing", "extra_voices", False),
        ("User", "user_added", True),
    ]
    assert [entry.name for entry in catalog.list_entries(query="xTr")] == ["Extra"]
    assert [entry.name for entry in catalog.list_entries(source="user_added")] == ["User"]
    with pytest.raises(CatalogError) as error:
        catalog.list_entries(source="unknown")
    assert error.value.code == "invalid_source"


def test_saves_valid_upload_at_exact_size_boundary(tmp_path):
    catalog = make_catalog(tmp_path)
    data = b"x" * MAX_UPLOAD_BYTES

    entry = catalog.save_upload("hello.MP3", "Greeting", data)

    assert entry.id == "extra_voices:Greeting.mp3"
    assert entry.name == "Greeting"
    assert entry.source == "extra_voices"
    assert entry.extension == ".mp3"
    assert entry.size == MAX_UPLOAD_BYTES
    assert entry.available is True
    assert catalog.audio_path(entry.id).read_bytes() == data


def test_saves_user_added_voice_for_voice_add_compatibility(tmp_path):
    catalog = make_catalog(tmp_path)

    entry = catalog.save_user_upload("reply.ogg", "Reply", b"user")

    assert entry.id == "user_added:Reply.ogg"
    assert catalog.refresh() == {"Reply": str(entry.path)}


def test_rejects_invalid_extension_and_duplicate_effective_keyword(tmp_path):
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "Taken.wav").write_bytes(b"builtin")
    catalog = make_catalog(tmp_path)

    with pytest.raises(CatalogError) as error:
        catalog.save_upload("bad.txt", "new", b"x")
    assert error.value.code == "invalid_extension"
    with pytest.raises(CatalogError) as error:
        catalog.save_upload("new.mp3", "taken", b"x")
    assert error.value.code == "duplicate_keyword"


def test_deletes_user_file_and_rejects_builtin_deletion(tmp_path):
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "Built.wav").write_bytes(b"builtin")
    (tmp_path / "data" / "user_added").mkdir(parents=True)
    (tmp_path / "data" / "user_added" / "Added.ogg").write_bytes(b"user")
    catalog = make_catalog(tmp_path)

    catalog.delete("user_added:Added.ogg")

    assert catalog.list_entries(source="user_added") == []
    with pytest.raises(CatalogError) as error:
        catalog.delete("builtin:Built.wav")
    assert error.value.code == "read_only"
    with pytest.raises(CatalogError) as error:
        catalog.resolve_entry("extra_voices:missing.mp3")
    assert error.value.code == "not_found"


def test_refresh_rebuilds_index_after_filesystem_mutation(tmp_path):
    extra = tmp_path / "data" / "extra_voices"
    extra.mkdir(parents=True)
    (extra / "Before.m4a").write_bytes(b"before")
    catalog = make_catalog(tmp_path)

    assert catalog.refresh() == {"Before": str(extra / "Before.m4a")}
    (extra / "Before.m4a").unlink()
    (extra / "After.wav").write_bytes(b"after")

    assert catalog.refresh() == {"After": str(extra / "After.wav")}


def test_parser_preserves_random_prefix_and_direct_keyword_contract():
    from request_parser import parse_request

    assert parse_request("normal keyword", True, "direct").kind == "keyword"
    assert parse_request("随机语音", True, "direct").kind == "random_all"
    assert parse_request("随机猫", True, "direct").kind == "ignore"
    assert parse_request("随机猫", True, "direct", raw_text="/随机猫").kind == "random_filter"
    assert parse_request("随机猫", True, "direct", raw_text="//随机猫").kind == "ignore"
    assert parse_request("#voice normal keyword", False, "prefix").keyword == "normal keyword"
