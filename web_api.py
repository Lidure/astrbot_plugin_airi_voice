"""Compatibility boundary for AstrBot Plugin Pages support.

Plugin Pages are discovered from a plugin's ``pages/`` directory by AstrBot.
Web API routes use ``Context.register_web_api`` and are added here by the
later route implementation task.
"""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegistrationResult:
    """Records which optional Dashboard features were registered."""

    pages_registered: bool
    api_registered: bool


def _has_discoverable_page(pages_dir: Path) -> bool:
    """Return whether AstrBot can discover a ``pages/<name>/index.html`` page."""

    if not pages_dir.is_dir():
        return False
    return any(
        page_dir.is_dir() and (page_dir / "index.html").is_file()
        for page_dir in pages_dir.iterdir()
    )


def register_web_features(context: Any, plugin: Any) -> RegistrationResult:
    """Detect Plugin Pages support without making it a plugin requirement.

    AstrBot discovers ``pages/<page_name>/index.html`` itself; there is no
    public static-page registration method. Concrete Web API routes are added
    by the route implementation once their callbacks are available.
    """

    try:
        register_web_api = context.register_web_api
        if not callable(register_web_api):
            raise AttributeError("register_web_api is not callable")
        pages_dir = Path(getattr(plugin, "plugin_dir")) / "pages"
    except (ImportError, AttributeError) as exc:
        LOGGER.warning("[AiriVoice] Plugin Pages/Web API is unavailable; WebUI is disabled: %s", exc)
        return RegistrationResult(False, False)
    except Exception as exc:
        LOGGER.warning("[AiriVoice] Plugin Pages/Web API is unavailable; WebUI is disabled: %s", exc)
        return RegistrationResult(False, False)

    try:
        pages_registered = _has_discoverable_page(pages_dir)
    except Exception as exc:
        LOGGER.warning("[AiriVoice] Plugin Pages/Web API is unavailable; WebUI is disabled: %s", exc)
        return RegistrationResult(False, False)

    return RegistrationResult(pages_registered=pages_registered, api_registered=False)
