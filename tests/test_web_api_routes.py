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
    def file_response(path, filename=None, content_type=None):
        return {
            "kind": "file",
            "path": Path(path),
            "filename": filename,
            "content_type": content_type,
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
        if keyword == "bad":
            raise CatalogError("invalid_keyword", "keyword is invalid")
        return self.entries[0]

    def delete(self, entry_id):
        self.calls.append(("delete", entry_id))
        if entry_id == "missing":
            raise CatalogError("not_found", "voice entry was not found")


class FakePlugin:
    def __init__(self, request, *, admin=True):
        self.catalog = FakeCatalog()
        self._request = request
        self._admin = admin
        self.refresh_count = 0

    def web_request_is_admin(self, username):
        assert username == self._request.username
        return self._admin

    def refresh_voice_catalog(self):
        self.refresh_count += 1


def make_routes(request, *, admin=True):
    from web_api import VoiceManagementRoutes

    plugin = FakePlugin(request, admin=admin)
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


def test_audio_uses_file_response_and_never_returns_path_json():
    routes, plugin = make_routes(FakeRequest())

    response = run(routes.get_audio, "builtin:Bell.wav")

    assert response["kind"] == "file"
    assert response["filename"] == "Bell.wav"
    assert response["content_type"] == "audio/wav"
    assert plugin.catalog.calls == [("audio", "builtin:Bell.wav")]


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
    failed = register_web_features(Context("/airi_voice/voices/reload"), Plugin())

    assert successful.api_registered is True
    assert [route[0] for route in successful_context.routes] == [
        "/airi_voice/voices",
        "/airi_voice/voices/<voice_id>/audio",
        "/airi_voice/voices/upload",
        "/airi_voice/voices/<voice_id>",
        "/airi_voice/voices/reload",
    ]
    assert failed.api_registered is False
