import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_catalog import VoiceEntry
from web_api import VoiceManagementRoutes


class FakeRequest:
    def __init__(self, body=None, username="admin"):
        self._body = body or {}
        self.query = {}
        self.username = username

    async def json(self, default=None):
        return self._body if self._body is not None else (default or {})


class FakeWeb:
    def __init__(self, request):
        self.request = request

    @staticmethod
    def json_response(payload, status_code=200):
        return {"status": status_code, "body": payload}


class FakeCatalog:
    def __init__(self):
        self.calls = []
        self.entry = VoiceEntry(
            id="builtin:Bell.wav",
            name="Bell",
            source="builtin",
            path=Path("/voices/Bell.wav"),
            extension=".wav",
            size=4,
            available=True,
        )

    def add_alias(self, entry_id, alias):
        self.calls.append(("add", entry_id, alias))
        return self.entry

    def remove_alias(self, entry_id, alias):
        self.calls.append(("remove", entry_id, alias))
        return self.entry


class FakePlugin:
    def __init__(self, request):
        self.catalog = FakeCatalog()
        self.request = request
        self.refresh_count = 0

    def web_request_is_admin(self, username):
        return username == "admin"

    def refresh_voice_catalog(self):
        self.refresh_count += 1


def run(handler):
    return asyncio.run(handler())


def test_alias_bridge_uses_fixed_endpoint_with_json_body():
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert 'bridge().apiPost("keywords/aliases/add", { voice_id: item.id, alias })' in script
    assert 'bridge().apiPost("keywords/aliases/remove", { voice_id: item.id, alias })' in script
    assert "keywords/aliases/add?voice_id=" not in script
    assert "keywords/aliases/remove?voice_id=" not in script


def test_alias_routes_read_voice_id_and_alias_from_post_json_body():
    request = FakeRequest({"voice_id": "builtin:Bell.wav", "alias": "响铃"})
    plugin = FakePlugin(request)
    routes = VoiceManagementRoutes(plugin, FakeWeb(request))

    added = run(routes.add_alias)
    assert added["status"] == 200
    assert plugin.catalog.calls[-1] == ("add", "builtin:Bell.wav", "响铃")

    removed = run(routes.remove_alias)
    assert removed["status"] == 200
    assert plugin.catalog.calls[-1] == ("remove", "builtin:Bell.wav", "响铃")
    assert plugin.refresh_count == 2


def test_upload_has_clear_success_feedback_next_to_form():
    page = Path("pages/airi-voice/index.html").read_text(encoding="utf-8")
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")
    styles = Path("pages/airi-voice/style.css").read_text(encoding="utf-8")

    assert 'id="upload-feedback"' in page
    assert 'aria-live="polite"' in page
    assert "showUploadFeedback" in script
    assert "上传成功" in script
    assert ".upload-feedback.is-success" in styles
    assert ".upload-feedback.is-error" in styles
