import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voice_catalog import VoiceEntry
from web_api import VoiceManagementRoutes


class FakeQuery(dict):
    def get(self, key, default=None, type=None):
        value = super().get(key, default)
        return type(value) if type is not None and value is not None else value


class FakeUpload:
    def __init__(self, filename: str, data: bytes):
        self.filename = filename
        self._data = data

    async def read(self):
        return self._data


class FakeRequest:
    def __init__(self, upload: FakeUpload):
        self.query = FakeQuery()
        self.username = "admin"
        self._upload = upload

    async def form(self):
        return {}

    async def files(self):
        return {"file": self._upload}


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
            id="extra_voices:自定义关键词.mp3",
            name="自定义关键词",
            source="extra_voices",
            path=Path("/tmp/自定义关键词.mp3"),
            extension=".mp3",
            size=5,
            available=True,
        )

    def save_upload(self, filename, keyword, data):
        self.calls.append((filename, keyword, data))
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


def test_plugin_page_upload_uses_fixed_bridge_endpoint_and_renamed_file():
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert 'bridge().upload("voices/upload", uploadFile)' in script
    assert "new File([file]" in script
    assert "voices/upload/${" not in script


def test_fixed_upload_route_derives_keyword_from_uploaded_filename():
    request = FakeRequest(FakeUpload("自定义关键词.mp3", b"audio"))
    plugin = FakePlugin(request)
    routes = VoiceManagementRoutes(plugin, FakeWeb(request))

    response = asyncio.run(routes.upload_voice())

    assert response["status"] == 200
    assert plugin.catalog.calls == [("自定义关键词.mp3", "自定义关键词", b"audio")]
    assert plugin.refresh_count == 1
