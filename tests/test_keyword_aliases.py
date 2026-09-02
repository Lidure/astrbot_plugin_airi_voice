import asyncio
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_catalog import CatalogError, VoiceCatalog, VoiceEntry
from web_api import VoiceManagementRoutes, register_web_features


def make_catalog(tmp_path, extra_voice_pool=()):
    return VoiceCatalog(tmp_path / "voices", tmp_path / "data", extra_voice_pool)


def test_aliases_persist_and_expand_trigger_map_without_changing_primary_refresh(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    voice_path = voices / "Morning.wav"
    voice_path.write_bytes(b"audio")
    catalog = make_catalog(tmp_path)
    entry = catalog.list_entries()[0]

    assert hasattr(catalog, "add_alias")
    catalog.add_alias(entry.id, "早安")
    catalog.add_alias(entry.id, "起床啦")

    assert catalog.refresh() == {"Morning": str(voice_path)}
    assert catalog.trigger_map() == {
        "Morning": str(voice_path),
        "早安": str(voice_path),
        "起床啦": str(voice_path),
    }
    assert catalog.aliases_for(entry.id) == ["早安", "起床啦"]

    reloaded = make_catalog(tmp_path)
    assert reloaded.aliases_for(entry.id) == ["早安", "起床啦"]
    assert reloaded.trigger_map()["早安"] == str(voice_path)
    assert (tmp_path / "data" / "keyword_aliases.json").is_file()


def test_aliases_are_globally_unique_against_primary_names_and_other_aliases(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "Alpha.wav").write_bytes(b"alpha")
    (voices / "Beta.wav").write_bytes(b"beta")
    catalog = make_catalog(tmp_path)
    entries = {entry.name: entry for entry in catalog.list_entries()}

    catalog.add_alias(entries["Alpha"].id, "Common")

    for entry_id, alias in (
        (entries["Alpha"].id, "alpha"),
        (entries["Beta"].id, "ALPHA"),
        (entries["Beta"].id, "common"),
    ):
        with pytest.raises(CatalogError) as error:
            catalog.add_alias(entry_id, alias)
        assert error.value.code == "duplicate_keyword"

    assert catalog.aliases_for(entries["Alpha"].id) == ["Common"]
    assert catalog.aliases_for(entries["Beta"].id) == []


def test_local_voice_deletion_cleans_aliases(tmp_path):
    voices = tmp_path / "voices"
    voices.mkdir()
    (voices / "Local.wav").write_bytes(b"local")
    catalog = make_catalog(tmp_path)
    entry = catalog.list_entries()[0]
    catalog.add_alias(entry.id, "本地别名")

    catalog.delete(entry.id)

    assert catalog.list_entries() == []
    assert "本地别名" not in catalog.trigger_map()
    reloaded = make_catalog(tmp_path)
    assert reloaded.trigger_map() == {}


def test_missing_configured_voice_keeps_alias_metadata_until_file_returns(tmp_path):
    configured = tmp_path / "data" / "managed" / "Remote.mp3"
    catalog = make_catalog(tmp_path, [str(configured)])
    entry = catalog.list_entries()[0]
    assert entry.available is False

    catalog.add_alias(entry.id, "远程别名")
    reloaded_missing = make_catalog(tmp_path, [str(configured)])
    assert reloaded_missing.aliases_for(entry.id) == ["远程别名"]
    assert "远程别名" not in reloaded_missing.trigger_map()

    configured.parent.mkdir(parents=True, exist_ok=True)
    configured.write_bytes(b"remote")
    reloaded_missing.refresh()
    assert reloaded_missing.trigger_map()["远程别名"] == str(configured.resolve())


def test_runtime_uses_alias_trigger_map_without_polluting_primary_lists_or_random_pool():
    source = Path("main.py").read_text(encoding="utf-8")

    assert "self.primary_voice_map: Dict[str, str] = {}" in source
    assert "self.primary_voice_map = self.catalog.refresh()" in source
    assert "self.voice_map = self.catalog.trigger_map()" in source
    assert "self.sorted_keys = sorted(self.primary_voice_map.keys())" in source
    assert "names = sorted(self.plugin.primary_voice_map.keys())" in source
    assert "candidates = list(self.plugin.primary_voice_map.keys())" in source
    assert "random.choice(list(self.primary_voice_map.keys()))" in source
    assert "name = random.choice(list(self.primary_voice_map.keys()))" in source
    assert "candidates = [name for name in self.primary_voice_map if match.group(1).strip() in name]" in source
    assert "random.choice(list(self.voice_map.keys()))" not in source
    assert "candidates = [name for name in self.voice_map if match.group(1).strip() in name]" not in source


class FakeQuery(dict):
    def get(self, key, default=None, type=None):
        value = super().get(key, default)
        return type(value) if type is not None and value is not None else value


class FakeRequest:
    def __init__(self, query=None, username="admin"):
        self.query = FakeQuery(query or {})
        self.username = username


class FakeWeb:
    def __init__(self, request):
        self.request = request

    @staticmethod
    def json_response(payload, status_code=200):
        return {"kind": "json", "status": status_code, "body": payload}


class FakeAliasCatalog:
    def __init__(self):
        self.entry = VoiceEntry(
            id="builtin:Bell.wav",
            name="Bell",
            source="builtin",
            path=Path("/voices/Bell.wav"),
            extension=".wav",
            size=4,
            available=True,
        )
        self.aliases = []
        self.calls = []

    def list_entries(self, query="", source=None):
        return [self.entry]

    def aliases_for(self, entry_id):
        self.calls.append(("aliases", entry_id))
        return list(self.aliases)

    def add_alias(self, entry_id, alias):
        self.calls.append(("add", entry_id, alias))
        self.aliases.append(alias)
        return self.entry

    def remove_alias(self, entry_id, alias):
        self.calls.append(("remove", entry_id, alias))
        self.aliases.remove(alias)
        return self.entry


class FakePlugin:
    def __init__(self, request):
        self.catalog = FakeAliasCatalog()
        self.request = request
        self.refresh_count = 0
        self.plugin_dir = Path(".")

    def web_request_is_admin(self, username):
        return username == "admin"

    def refresh_voice_catalog(self):
        self.refresh_count += 1


def run(handler, *args):
    return asyncio.run(handler(*args))


def test_keyword_web_api_lists_aliases_and_mutates_them_on_fixed_routes():
    request = FakeRequest()
    plugin = FakePlugin(request)
    routes = VoiceManagementRoutes(plugin, FakeWeb(request))

    assert hasattr(routes, "list_keywords")
    listed = run(routes.list_keywords)
    assert listed["status"] == 200
    assert listed["body"]["items"][0]["name"] == "Bell"
    assert listed["body"]["items"][0]["aliases"] == []

    request.query = FakeQuery({"voice_id": "builtin:Bell.wav", "alias": "响铃"})
    added = run(routes.add_alias)
    assert added["status"] == 200
    assert plugin.catalog.calls[-1] == ("add", "builtin:Bell.wav", "响铃")
    assert plugin.refresh_count == 1

    removed = run(routes.remove_alias)
    assert removed["status"] == 200
    assert plugin.catalog.calls[-1] == ("remove", "builtin:Bell.wav", "响铃")
    assert plugin.refresh_count == 2


def test_keyword_alias_mutations_require_dashboard_admin_permission():
    request = FakeRequest({"voice_id": "builtin:Bell.wav", "alias": "响铃"}, username="guest")
    plugin = FakePlugin(request)
    routes = VoiceManagementRoutes(plugin, FakeWeb(request))

    assert hasattr(routes, "add_alias")
    response = run(routes.add_alias)
    assert response["status"] == 403
    assert plugin.catalog.calls == []


def test_registration_includes_fixed_keyword_management_routes(tmp_path):
    class Context:
        def __init__(self):
            self.routes = []

        def register_web_api(self, route, view_handler, methods, desc):
            self.routes.append((route, view_handler, methods, desc))

    class Plugin(FakePlugin):
        plugin_dir = tmp_path

        def __init__(self):
            super().__init__(FakeRequest())

    page_dir = tmp_path / "pages" / "airi-voice"
    page_dir.mkdir(parents=True)
    (page_dir / "index.html").write_text("ok", encoding="utf-8")
    context = Context()

    result = register_web_features(context, Plugin())

    assert result.api_registered is True
    routes = [item[0] for item in context.routes]
    assert "/astrbot_plugin_airi_voice/keywords" in routes
    assert "/astrbot_plugin_airi_voice/keywords/aliases/add" in routes
    assert "/astrbot_plugin_airi_voice/keywords/aliases/remove" in routes


def test_webui_has_audio_and_keyword_tabs_with_alias_management_controls():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")
    styles = Path("pages/airi-voice/style.css").read_text(encoding="utf-8")

    assert 'id="audio-tab"' in page
    assert 'id="keywords-tab"' in page
    assert 'id="audio-management-view"' in page
    assert 'id="keyword-management-view"' in page
    assert 'id="keyword-list"' in page
    assert 'data-view="audio"' in page and 'data-view="keywords"' in page
    assert 'bridge().apiGet("keywords")' in script
    assert 'bridge().apiPost("keywords/aliases/add", { voice_id: item.id, alias })' in script
    assert 'bridge().apiPost("keywords/aliases/remove", { voice_id: item.id, alias })' in script
    assert "renderKeywords" in script
    assert ".management-tabs" in styles
    assert ".alias-chip" in styles


def test_keyword_alias_feature_is_in_v210_release():
    metadata = Path("metadata.yaml").read_text(encoding="utf-8")
    main = Path("main.py").read_text(encoding="utf-8")

    assert "version: v2.10.0" in metadata
    assert '"2.10.0"' in main
