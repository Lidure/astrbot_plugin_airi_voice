import asyncio
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_catalog import CatalogError, VoiceEntry


class FakeQuery(dict):
    def get(self, key, default=None, type=None):
        value = super().get(key, default)
        return type(value) if type is not None and value is not None else value


class FakeUpload:
    def __init__(self, filename, data):
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


class FakeRequest:
    def __init__(self, *, query=None, form=None, files=None, username="admin"):
        self.query = FakeQuery(query or {})
        self._form = form or {}
        self._files = files or {}
        self.username = username

    async def form(self):
        return self._form

    async def files(self):
        return self._files


class FakeWeb:
    def __init__(self, request):
        self.request = request

    @staticmethod
    def json_response(payload, status_code=200):
        return {"kind": "json", "status": status_code, "body": payload}

    @staticmethod
    def file_response(path, filename=None, content_type=None, headers=None):
        return {
            "kind": "file",
            "path": Path(path),
            "filename": filename,
            "content_type": content_type,
            "headers": headers,
        }


class FakeCatalog:
    def __init__(self):
        self.entries = [
            VoiceEntry(
                id="builtin:Bell.wav",
                name="Bell",
                source="builtin",
                path=Path("/secret/audio-root/Bell.wav"),
                extension=".wav",
                size=4,
                available=True,
            )
        ]
        self.calls = []

    def list_entries(self, query="", source=None):
        self.calls.append(("list", query, source))
        return self.entries

    def audio_path(self, entry_id):
        self.calls.append(("audio", entry_id))
        if entry_id == "missing":
            raise CatalogError("not_found", "voice entry was not found")
        return self.entries[0].path

    def save_upload(self, filename, keyword, data):
        self.calls.append(("upload", filename, keyword, data))
        if any(part in keyword for part in ("/", "\\", "..", "\n")):
            raise CatalogError("invalid_keyword", "keyword is invalid")
        if keyword == "bad":
            raise CatalogError("invalid_keyword", "keyword is invalid")
        return self.entries[0]

    def delete(self, entry_id):
        self.calls.append(("delete", entry_id))
        if entry_id == "missing":
            raise CatalogError("not_found", "voice entry was not found")


class FakePlugin:
    def __init__(self, request, *, admin=True, admin_mode=None, whitelist=()):
        self.catalog = FakeCatalog()
        self._request = request
        self._admin = admin
        self.admin_mode = admin_mode
        self.admin_whitelist = set(whitelist)
        self.refresh_count = 0

    def web_request_is_admin(self, username):
        assert username == self._request.username
        if self.admin_mode == "admin":
            return bool(username and username.strip())
        if self.admin_mode == "all":
            return True
        if self.admin_mode == "whitelist":
            return username in self.admin_whitelist
        return self._admin

    def refresh_voice_catalog(self):
        self.refresh_count += 1


def make_routes(request, *, admin=True, admin_mode=None, whitelist=()):
    from web_api import VoiceManagementRoutes

    plugin = FakePlugin(request, admin=admin, admin_mode=admin_mode, whitelist=whitelist)
    return VoiceManagementRoutes(plugin, FakeWeb(request)), plugin


def run(handler, *args):
    return asyncio.run(handler(*args))


def test_list_returns_only_public_metadata_and_query_filters():
    routes, plugin = make_routes(FakeRequest(query={"q": "ell", "source": "builtin"}))

    response = run(routes.list_voices)

    assert response == {
        "kind": "json",
        "status": 200,
        "body": {
            "items": [
                {
                    "id": "builtin:Bell.wav",
                    "name": "Bell",
                    "source": "builtin",
                    "extension": ".wav",
                    "size": 4,
                    "available": True,
                }
            ],
            "total": 1,
        },
    }
    assert plugin.catalog.calls == [("list", "ell", "builtin")]


def test_list_treats_empty_source_filter_as_all_sources():
    routes, plugin = make_routes(FakeRequest(query={"q": "", "source": ""}))

    response = run(routes.list_voices)

    assert response["status"] == 200
    assert plugin.catalog.calls == [("list", "", None)]


def test_audio_uses_file_response_and_never_returns_path_json():
    routes, plugin = make_routes(FakeRequest())
    plugin.catalog.audio_path = lambda entry_id: (plugin.catalog.calls.append(("audio", entry_id)) or Path(__file__))

    response = run(routes.get_audio, "builtin:Bell.wav")

    assert response["kind"] == "json"
    assert response["status"] == 200
    assert response["body"]["filename"] == "test_web_api_routes.py"
    assert response["body"]["content_type"] == "text/x-python"
    assert response["body"]["audio_hex"]
    assert plugin.catalog.calls == [("audio", "builtin:Bell.wav")]


def test_audio_accepts_url_encoded_voice_id_from_dashboard_bridge():
    routes, plugin = make_routes(FakeRequest())

    response = run(routes.get_audio, "builtin%3ABell.wav")

    assert response["kind"] == "json"
    assert plugin.catalog.calls == [("audio", "builtin%3ABell.wav")]


@pytest.mark.parametrize("operation", ["upload", "delete", "reload"])
def test_mutations_return_403_without_dashboard_admin_permission(operation):
    request = FakeRequest(
        form={"keyword": "new"}, files={"file": FakeUpload("new.mp3", b"audio")}
    )
    routes, plugin = make_routes(request, admin=False)

    handler, args = {
        "upload": (routes.upload_voice, ()),
        "delete": (routes.delete_voice, ("builtin:Bell.wav",)),
        "reload": (routes.reload_voices, ()),
    }[operation]
    response = run(handler, *args)

    assert response == {
        "kind": "json",
        "status": 403,
        "body": {"error": {"code": "forbidden", "message": "administrator permission is required"}},
    }
    assert plugin.catalog.calls == []
    assert plugin.refresh_count == 0


def test_admin_upload_dispatches_catalog_and_refreshes_plugin_state():
    request = FakeRequest(
        form={"keyword": "new"}, files={"file": FakeUpload("new.mp3", b"audio")}
    )
    routes, plugin = make_routes(request)

    response = run(routes.upload_voice)

    assert response["status"] == 200
    assert response["body"]["item"]["id"] == "builtin:Bell.wav"
    assert plugin.catalog.calls == [("upload", "new.mp3", "new", b"audio")]
    assert plugin.refresh_count == 1


def test_dynamic_keyword_upload_uses_path_keyword_and_catalog_validation():
    request = FakeRequest(files={"file": FakeUpload("new.mp3", b"audio")})
    routes, plugin = make_routes(request)

    response = run(routes.upload_voice, "path keyword")
    unsafe_response = run(routes.upload_voice, "../secret")

    assert response["status"] == 200
    assert plugin.catalog.calls[0] == ("upload", "new.mp3", "path keyword", b"audio")
    assert unsafe_response == {
        "kind": "json",
        "status": 400,
        "body": {"error": {"code": "invalid_keyword", "message": "keyword is invalid"}},
    }


def test_direct_upload_client_can_fallback_to_query_keyword():
    request = FakeRequest(
        query={"keyword": "query keyword"}, files={"file": FakeUpload("new.mp3", b"audio")}
    )
    routes, plugin = make_routes(request)

    response = run(routes.upload_voice)

    assert response["status"] == 200
    assert plugin.catalog.calls == [("upload", "new.mp3", "query keyword", b"audio")]


def test_admin_delete_and_reload_dispatch_catalog_and_refresh_state():
    routes, plugin = make_routes(FakeRequest())

    delete_response = run(routes.delete_voice, "builtin:Bell.wav")
    reload_response = run(routes.reload_voices)

    assert delete_response["body"] == {"deleted": True}
    assert reload_response["body"] == {"reloaded": True, "total": 1}
    assert plugin.catalog.calls == [("delete", "builtin:Bell.wav"), ("list", "", None)]
    assert plugin.refresh_count == 2


def test_catalog_errors_map_to_400_or_404_stable_json_errors():
    upload_request = FakeRequest(
        form={"keyword": "bad"}, files={"file": FakeUpload("bad.mp3", b"audio")}
    )
    upload_routes, _ = make_routes(upload_request)
    missing_routes, _ = make_routes(FakeRequest())

    upload_response = run(upload_routes.upload_voice)
    missing_response = run(missing_routes.get_audio, "missing")

    assert upload_response == {
        "kind": "json",
        "status": 400,
        "body": {"error": {"code": "invalid_keyword", "message": "keyword is invalid"}},
    }
    assert missing_response == {
        "kind": "json",
        "status": 404,
        "body": {"error": {"code": "not_found", "message": "voice entry was not found"}},
    }


def test_route_callback_exception_returns_safe_500_without_catalog_details():
    routes, plugin = make_routes(FakeRequest())

    def explode(*args, **kwargs):
        raise RuntimeError("/secret/audio-root must not escape")

    plugin.catalog.list_entries = explode
    response = run(routes.list_voices)

    assert response == {
        "kind": "json",
        "status": 500,
        "body": {"error": {"code": "internal_error", "message": "unable to list voices"}},
    }


def test_registration_registers_public_routes_and_swallows_route_registration_failure(tmp_path):
    from web_api import register_web_features

    class Context:
        def __init__(self, fail_on=None):
            self.fail_on = fail_on
            self.routes = []

        def register_web_api(self, route, view_handler, methods, desc):
            if route == self.fail_on:
                raise RuntimeError("route registration failed")
            self.routes.append((route, view_handler, methods, desc))

    class Plugin:
        plugin_dir = tmp_path
        catalog = FakeCatalog()

        def web_request_is_admin(self, username):
            return True

        def refresh_voice_catalog(self):
            pass

    successful_context = Context()
    successful = register_web_features(successful_context, Plugin())
    failed = register_web_features(Context("/astrbot_plugin_airi_voice/voices/reload"), Plugin())

    assert successful.api_registered is True
    assert [route[0] for route in successful_context.routes] == [
        "/astrbot_plugin_airi_voice/voices",
        "/astrbot_plugin_airi_voice/voices/<voice_id>/audio",
        "/astrbot_plugin_airi_voice/voices/upload",
        "/astrbot_plugin_airi_voice/voices/upload/<keyword>",
        "/astrbot_plugin_airi_voice/voices/<voice_id>",
        "/astrbot_plugin_airi_voice/voices/<voice_id>/delete",
        "/astrbot_plugin_airi_voice/voices/reload",
    ]
    assert failed.api_registered is False


def test_dashboard_admin_mode_requires_configured_webui_username():
    from web_api import dashboard_request_is_admin

    class Policy:
        admin_mode = "admin"

        def _check_admin(self, event):
            raise AssertionError("admin-mode Dashboard identity must use trusted username")

    policy = Policy()
    policy.config = {"webui_admin_users": ["dashboard-user"]}

    assert dashboard_request_is_admin(policy, "dashboard-user") is True
    assert dashboard_request_is_admin(policy, "other-user") is False
    assert dashboard_request_is_admin(policy, "  ") is False
    assert dashboard_request_is_admin(policy, None) is False


@pytest.mark.parametrize(
    "config",
    [None, {}, {"webui_admin_users": "dashboard-user"}, {"webui_admin_users": ["dashboard-user", 7]}],
)
def test_dashboard_admin_mode_denies_missing_or_invalid_webui_allowlist(config):
    from web_api import dashboard_request_is_admin

    class Policy:
        admin_mode = "admin"
        _check_admin = lambda self, event: True

    policy = Policy()
    if config is not None:
        policy.config = config

    assert dashboard_request_is_admin(policy, "dashboard-user") is False


def test_dashboard_all_and_whitelist_modes_keep_existing_semantics():
    from web_api import dashboard_request_is_admin

    class Policy:
        def __init__(self, mode, whitelist=()):
            self.admin_mode = mode
            self.admin_whitelist = set(whitelist)

        def _check_admin(self, event):
            if self.admin_mode == "all":
                return True
            return event.sender_id in self.admin_whitelist or event.sender_name in self.admin_whitelist

    assert dashboard_request_is_admin(Policy("all"), None) is True
    assert dashboard_request_is_admin(Policy("whitelist", ["allowed"]), "allowed") is True
    assert dashboard_request_is_admin(Policy("whitelist", ["allowed"]), "other") is False
