import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from request_parser import ParsedRequest, parse_request


def _audio_compat_module():
    spec = importlib.util.find_spec("audio_compat")
    assert spec is not None, "audio_compat module is not implemented"
    return importlib.import_module("audio_compat")


def test_exact_random_named_voice_wins_over_unprefixed_random_syntax():
    result = parse_request(
        "随机猫",
        False,
        "direct",
        known_keywords={"随机猫", "猫"},
    )
    assert result == ParsedRequest("keyword", "随机猫")


def test_explicit_slash_random_command_still_wins_over_voice_keyword():
    result = parse_request(
        "随机猫",
        True,
        "direct",
        raw_text="/随机猫",
        known_keywords={"随机猫"},
    )
    assert result == ParsedRequest("random_filter", "猫")


def test_reserved_random_voice_phrase_remains_random_command():
    result = parse_request(
        "随机语音",
        False,
        "direct",
        known_keywords={"随机语音"},
    )
    assert result == ParsedRequest("random_all")


def test_wav_send_path_is_passthrough(tmp_path):
    module = _audio_compat_module()
    source = tmp_path / "voice.wav"
    source.write_bytes(b"RIFFdummy-WAVE")
    compat = module.AudioSendCompat(tmp_path / "cache")

    assert asyncio.run(compat.prepare(source)) == str(source.resolve())


def test_non_wav_conversion_is_cached_and_reused(tmp_path, monkeypatch):
    module = _audio_compat_module()
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"fake-mp3")
    calls = []

    async def fake_convert(source_path, target_path):
        calls.append((source_path, target_path))
        target_path.write_bytes(b"RIFFconverted-WAVE")

    monkeypatch.setattr(module, "_convert_standard_audio", fake_convert)
    compat = module.AudioSendCompat(tmp_path / "cache")

    first = asyncio.run(compat.prepare(source))
    second = asyncio.run(compat.prepare(source))

    assert first == second
    assert Path(first).suffix == ".wav"
    assert Path(first).read_bytes() == b"RIFFconverted-WAVE"
    assert len(calls) == 1


def test_silk_decoder_is_shared_with_web_preview():
    module = _audio_compat_module()
    web_api = (ROOT / "web_api.py").read_text(encoding="utf-8")
    assert hasattr(module, "decode_silk_to_wav_bytes")
    assert "decode_silk_to_wav_bytes" in web_api


def test_all_chat_voice_sends_use_plugin_compatibility_layer():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "AudioSendCompat" in main
    assert "async def _record_for_voice" in main
    assert "await self._record_for_voice(" in main
    assert "await self.plugin._record_for_voice(" in main


def test_release_version_is_v2_10_0():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "version: v2.10.0" in metadata
    assert '"2.10.0"' in main
