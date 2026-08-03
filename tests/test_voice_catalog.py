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


def test_audio_path_accepts_url_encoded_entry_id(tmp_path):
    (tmp_path / "voices").mkdir()
    (tmp_path / "voices" / "Bell.wav").write_bytes(b"bell")
    catalog = make_catalog(tmp_path)

    assert catalog.audio_path("builtin%3ABell.wav") == (tmp_path / "voices" / "Bell.wav").resolve()


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


def test_configured_voice_pool_accepts_absolute_files_under_plugin_data_root(tmp_path):
    configured = tmp_path / "data" / "managed" / "Configured.mp3"
    configured.parent.mkdir(parents=True)
    configured.write_bytes(b"configured")

    catalog = make_catalog(tmp_path, [str(configured)])

    entry = next(item for item in catalog.list_entries() if item.name == "Configured")
    assert entry.source == "extra_voices"
    assert entry.available is True
    assert entry.path == configured.resolve()
    assert catalog.audio_path(entry.id) == configured.resolve()


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


@pytest.mark.parametrize("extension", (".silk", ".amr", ".flac", ".m4a"))
def test_saves_all_supported_upload_extensions(tmp_path, extension):
    catalog = make_catalog(tmp_path)

    entry = catalog.save_upload(f"sample{extension}", "Sample", b"audio")

    assert entry.extension == extension
    assert catalog.audio_path(entry.id).suffix == extension


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


@pytest.mark.parametrize(
    ("first_source", "second_source"),
    [
        ("builtin", "user_added"),
        ("builtin", "extra_voices"),
        ("user_added", "extra_voices"),
    ],
)
def test_refresh_rejects_case_insensitive_keywords_colliding_across_sources(
    tmp_path, first_source, second_source
):
    roots = {
        "builtin": tmp_path / "voices",
        "user_added": tmp_path / "data" / "user_added",
        "extra_voices": tmp_path / "data" / "extra_voices",
    }
    roots[first_source].mkdir(parents=True)
    roots[second_source].mkdir(parents=True, exist_ok=True)
    (roots[first_source] / "Alert.wav").write_bytes(b"first")
    (roots[second_source] / "aLeRt.ogg").write_bytes(b"second")

    with pytest.raises(CatalogError) as error:
        make_catalog(tmp_path)

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
