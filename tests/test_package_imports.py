import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_as_plugin_module(module_name: str, filename: str):
    package_name = module_name.rsplit(".", 1)[0]
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT)]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(module_name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_web_modules_import_inside_astrbot_plugin_package(monkeypatch):
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if Path(entry or ".").resolve() != ROOT],
    )
    original_modules = {
        name: sys.modules.get(name)
        for name in ("voice_catalog", "airi_plugin", "airi_plugin.voice_catalog", "airi_plugin.web_api")
    }
    try:
        sys.modules.pop("voice_catalog", None)
        sys.modules.pop("airi_plugin.voice_catalog", None)
        sys.modules.pop("airi_plugin.web_api", None)

        catalog = _load_as_plugin_module("airi_plugin.voice_catalog", "voice_catalog.py")
        web_api = _load_as_plugin_module("airi_plugin.web_api", "web_api.py")

        assert web_api.VoiceEntry is catalog.VoiceEntry
    finally:
        for name in ("airi_plugin.voice_catalog", "airi_plugin.web_api", "airi_plugin"):
            sys.modules.pop(name, None)
        if original_modules["voice_catalog"] is not None:
            sys.modules["voice_catalog"] = original_modules["voice_catalog"]
