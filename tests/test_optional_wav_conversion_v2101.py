import asyncio
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import audio_compat


class FakeCompat:
    def __init__(self):
        self.calls = []

    async def prepare(self, path):
        self.calls.append(str(path))
        return str(Path(path).with_suffix(".wav"))


def test_wav_conversion_config_exists_and_defaults_off():
    schema = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8"))
    option = schema["convert_audio_to_wav"]
    assert option["type"] == "bool"
    assert option["default"] is False


def test_prepare_voice_path_bypasses_converter_when_disabled(tmp_path):
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"fake")
    compat = FakeCompat()

    assert hasattr(audio_compat, "prepare_voice_path")
    result = asyncio.run(audio_compat.prepare_voice_path(source, False, compat))

    assert result == str(source.resolve())
    assert compat.calls == []


def test_prepare_voice_path_uses_converter_when_enabled(tmp_path):
    source = tmp_path / "voice.mp3"
    source.write_bytes(b"fake")
    compat = FakeCompat()

    assert hasattr(audio_compat, "prepare_voice_path")
    result = asyncio.run(audio_compat.prepare_voice_path(source, True, compat))

    assert result == str(source.with_suffix(".wav"))
    assert compat.calls == [str(source)]


def test_main_wires_config_into_voice_record_preparation():
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'self.convert_audio_to_wav = bool(self.config.get("convert_audio_to_wav", False))' in main
    assert "prepare_voice_path(" in main
    assert "self.convert_audio_to_wav" in main


def test_release_version_is_v2_10_1():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")
    main = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "version: v2.10.2" in metadata
    assert '"2.10.2"' in main
