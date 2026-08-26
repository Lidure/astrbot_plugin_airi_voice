import asyncio
import io
import sys
import wave
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_random_dispatch_can_only_be_claimed_once_per_event():
    from request_parser import claim_random_dispatch

    class Event:
        pass

    first_event = Event()
    assert claim_random_dispatch(first_event) is True
    assert claim_random_dispatch(first_event) is False
    assert claim_random_dispatch(Event()) is True


def test_builtin_voice_can_be_deleted_from_catalog(tmp_path):
    from voice_catalog import VoiceCatalog

    voices = tmp_path / "voices"
    voices.mkdir()
    builtin = voices / "打卡啦摩托.silk"
    builtin.write_bytes(b"silk")
    catalog = VoiceCatalog(voices, tmp_path / "data")

    catalog.delete("builtin:打卡啦摩托.silk")

    assert builtin.exists() is False
    assert catalog.list_entries(source="builtin") == []


def test_configured_extra_pool_entry_remains_read_only(tmp_path):
    from voice_catalog import CatalogError, VoiceCatalog

    configured = tmp_path / "data" / "managed" / "Configured.mp3"
    configured.parent.mkdir(parents=True)
    configured.write_bytes(b"configured")
    catalog = VoiceCatalog(tmp_path / "voices", tmp_path / "data", [str(configured)])
    entry = next(item for item in catalog.list_entries() if item.name == "Configured")

    with pytest.raises(CatalogError) as error:
        catalog.delete(entry.id)

    assert error.value.code == "read_only"
    assert configured.exists() is True


class _FakeQuery(dict):
    def get(self, key, default=None, type=None):
        value = super().get(key, default)
        return type(value) if type is not None and value is not None else value


class _FakeRequest:
    query = _FakeQuery()
    username = "admin"


class _FakeWeb:
    request = _FakeRequest()

    @staticmethod
    def json_response(payload, status_code=200):
        return {"kind": "json", "status": status_code, "body": payload}


class _PreviewPlugin:
    def __init__(self, catalog):
        self.catalog = catalog

    def web_request_is_admin(self, username):
        return True


def test_silk_preview_is_transcoded_to_browser_playable_wav(tmp_path, monkeypatch):
    import web_api
    from voice_catalog import VoiceCatalog

    voices = tmp_path / "voices"
    voices.mkdir()
    silk = voices / "打卡啦摩托.silk"
    silk.write_bytes(b"raw-silk")
    catalog = VoiceCatalog(voices, tmp_path / "data")
    routes = web_api.VoiceManagementRoutes(_PreviewPlugin(catalog), _FakeWeb())
    wav_bytes = b"RIFF-test-wav"
    monkeypatch.setattr(web_api, "_decode_silk_to_wav", lambda path: wav_bytes)

    response = asyncio.run(routes.get_audio("builtin:打卡啦摩托.silk"))

    assert response["status"] == 200
    assert response["body"]["filename"] == "打卡啦摩托.wav"
    assert response["body"]["content_type"] == "audio/wav"
    assert response["body"]["audio_hex"] == wav_bytes.hex()


def test_silk_decoder_wraps_pcm_as_valid_wav(tmp_path, monkeypatch):
    import web_api

    silk = tmp_path / "voice.silk"
    silk.write_bytes(b"raw-silk")
    pcm = b"\x00\x00\x01\x00" * 20

    class FakePySilk:
        @staticmethod
        def decode(source, destination, sample_rate):
            assert sample_rate == 24000
            assert source.read() == b"raw-silk"
            destination.write(pcm)

    monkeypatch.setitem(sys.modules, "pysilk", FakePySilk)

    wav_bytes = web_api._decode_silk_to_wav(silk)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 24000
        assert wav_file.readframes(wav_file.getnframes()) == pcm


def test_webui_delete_button_allows_builtin_but_keeps_configured_pool_read_only():
    script = Path("pages/airi-voice/app.js").read_text(encoding="utf-8")

    assert 'item.source === "builtin"' not in script
    assert 'item.id.startsWith("extra_voices:configured/")' in script
