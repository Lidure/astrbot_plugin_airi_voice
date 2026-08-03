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
