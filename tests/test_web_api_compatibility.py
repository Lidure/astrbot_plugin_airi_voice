import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_registration_failure_does_not_raise():
    class BrokenContext:
        def __getattr__(self, name):
            raise AttributeError(name)

    from web_api import register_web_features
    result = register_web_features(BrokenContext(), object())
    assert result.pages_registered is False
    assert result.api_registered is False


def test_registers_a_discoverable_static_page_when_web_api_is_supported(tmp_path):
    class SupportedContext:
        def register_web_api(self, route, view_handler, methods, desc):
            raise AssertionError("Task 1 must not register route behavior")

    class Plugin:
        plugin_dir = tmp_path

    page = tmp_path / "pages" / "airi-voice"
    page.mkdir(parents=True)
    (page / "index.html").write_text("<!doctype html>", encoding="utf-8")

    from web_api import register_web_features
    result = register_web_features(SupportedContext(), Plugin())

    assert result.pages_registered is True
    assert result.api_registered is False


def test_does_not_report_pages_registered_without_a_discoverable_index(tmp_path):
    class SupportedContext:
        def register_web_api(self, route, view_handler, methods, desc):
            raise AssertionError("Task 1 must not register route behavior")

    class Plugin:
        plugin_dir = tmp_path

    (tmp_path / "pages" / "airi-voice").mkdir(parents=True)

    from web_api import register_web_features
    result = register_web_features(SupportedContext(), Plugin())

    assert result.pages_registered is False
    assert result.api_registered is False


def test_register_web_api_access_error_does_not_raise(tmp_path):
    class RaisingContext:
        @property
        def register_web_api(self):
            raise RuntimeError("registration unavailable")

    class Plugin:
        plugin_dir = tmp_path

    from web_api import register_web_features
    result = register_web_features(RaisingContext(), Plugin())

    assert result.pages_registered is False
    assert result.api_registered is False
