"""Optional AstrBot Plugin Pages routes for Airi Voice.

AstrBot is intentionally imported only while a registered handler executes so
older AstrBot versions can still load the chat plugin without WebUI support.
"""

from dataclasses import dataclass
import inspect
import logging
import mimetypes
from pathlib import Path
from typing import Any

if __package__:
    from .voice_catalog import CatalogError, VoiceEntry
else:
    from voice_catalog import CatalogError, VoiceEntry


LOGGER = logging.getLogger(__name__)
PLUGIN_NAME = "astrbot_plugin_airi_voice"


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


def _runtime_web_api() -> Any:
    """Load AstrBot's documented request/response helpers only when needed."""

    from astrbot.api.web import file_response, json_response, request

    return _WebApiPrimitives(request=request, json_response=json_response, file_response=file_response)


@dataclass(frozen=True)
class _WebApiPrimitives:
    request: Any
    json_response: Any
    file_response: Any


class _DashboardRequestEvent:
    """Minimal event shape used only to preserve existing whitelist/all checks."""

    def __init__(self, username: Any):
        self.sender_id = username
        self.user_id = username
        self.sender_name = username
        self.nickname = username


def dashboard_request_is_admin(plugin: Any, username: Any) -> bool:
    """Apply chat admin policy to a trusted authenticated Dashboard username.

    AstrBot supplies ``request.username`` only from its authenticated Plugin
    Pages context. In ``admin`` mode, the username must also be present in the
    plugin config's ``webui_admin_users`` list; absent or malformed config is
    denied. The existing plugin policy remains authoritative for ``all`` and
    ``whitelist``.
    """

    if getattr(plugin, "admin_mode", None) == "admin":
        if not isinstance(username, str) or not username.strip():
            return False
        config = getattr(plugin, "config", None)
        webui_admin_users = config.get("webui_admin_users") if isinstance(config, dict) else None
        if not isinstance(webui_admin_users, list):
            return False
        if any(not isinstance(user, str) for user in webui_admin_users):
            return False
        return username in webui_admin_users
    return bool(plugin._check_admin(_DashboardRequestEvent(username)))


class VoiceManagementRoutes:
    """Thin, independently testable handlers around the safe voice catalog."""

    def __init__(self, plugin: Any, web_api: Any = None):
        self.plugin = plugin
        self.web_api = web_api

    def _web(self) -> Any:
        return self.web_api if self.web_api is not None else _runtime_web_api()

    def _json(self, payload: dict[str, Any], status_code: int = 200) -> Any:
        response = self._web().json_response
        try:
            return response(payload, status_code=status_code)
        except TypeError:
            if status_code == 200:
                return response(payload)
            return payload, status_code

    def _error(self, code: str, message: str, status_code: int) -> Any:
        return self._json({"error": {"code": code, "message": message}}, status_code)

    def _catalog_error(self, error: CatalogError) -> Any:
        status_code = 404 if error.code == "not_found" else 400
        return self._error(error.code, error.message, status_code)

    def _is_admin(self) -> bool:
        username = getattr(self._web().request, "username", None)
        return bool(self.plugin.web_request_is_admin(username))

    def _forbidden(self) -> Any:
        return self._error("forbidden", "administrator permission is required", 403)

    @staticmethod
    def _entry_json(entry: VoiceEntry) -> dict[str, Any]:
        return {
            "id": entry.id,
            "name": entry.name,
            "source": entry.source,
            "extension": entry.extension,
            "size": entry.size,
            "available": entry.available,
        }

    async def list_voices(self) -> Any:
        try:
            query = self._web().request.query
            source = query.get("source")
            if isinstance(source, str):
                source = source.strip() or None
            entries = self.plugin.catalog.list_entries(
                query=query.get("q", ""), source=source
            )
            items = [self._entry_json(entry) for entry in entries]
            return self._json({"items": items, "total": len(items)})
        except CatalogError as error:
            return self._catalog_error(error)
        except Exception:
            LOGGER.exception("[AiriVoice] voice list WebUI request failed")
            return self._error("internal_error", "unable to list voices", 500)

    async def get_audio(self, voice_id: str) -> Any:
        try:
            path = self.plugin.catalog.audio_path(voice_id)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return self._json(
                {
                    "filename": path.name,
                    "content_type": content_type,
                    "audio_hex": path.read_bytes().hex(),
                }
            )
        except CatalogError as error:
            return self._catalog_error(error)
        except Exception:
            LOGGER.exception("[AiriVoice] voice audio WebUI request failed")
            return self._error("internal_error", "unable to load voice audio", 500)

    async def upload_voice(self, keyword: str | None = None) -> Any:
        if not self._is_admin():
            return self._forbidden()
        try:
            request = self._web().request
            form = await request.form() if keyword is None else {}
            upload = (await request.files()).get("file")
            if upload is None or not getattr(upload, "filename", None):
                raise CatalogError("invalid_upload", "an audio file is required")
            data = upload.read() if callable(getattr(upload, "read", None)) else None
            if inspect.isawaitable(data):
                data = await data
            if keyword is None:
                keyword = form.get("keyword") or request.query.get("keyword", "")
            entry = self.plugin.catalog.save_upload(upload.filename, keyword, data)
            self.plugin.refresh_voice_catalog()
            return self._json({"item": self._entry_json(entry)})
        except CatalogError as error:
            return self._catalog_error(error)
        except Exception:
            LOGGER.exception("[AiriVoice] voice upload WebUI request failed")
            return self._error("internal_error", "unable to upload voice", 500)

    async def delete_voice(self, voice_id: str) -> Any:
        if not self._is_admin():
            return self._forbidden()
        try:
            self.plugin.catalog.delete(voice_id)
            self.plugin.refresh_voice_catalog()
            return self._json({"deleted": True})
        except CatalogError as error:
            return self._catalog_error(error)
        except Exception:
            LOGGER.exception("[AiriVoice] voice deletion WebUI request failed")
            return self._error("internal_error", "unable to delete voice", 500)

    async def reload_voices(self) -> Any:
        if not self._is_admin():
            return self._forbidden()
        try:
            self.plugin.refresh_voice_catalog()
            return self._json({"reloaded": True, "total": len(self.plugin.catalog.list_entries())})
        except CatalogError as error:
            return self._catalog_error(error)
        except Exception:
            LOGGER.exception("[AiriVoice] voice reload WebUI request failed")
            return self._error("internal_error", "unable to reload voices", 500)


def register_web_features(context: Any, plugin: Any) -> RegistrationResult:
    """Register optional WebUI callbacks without making Web API support required."""

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
        routes = VoiceManagementRoutes(plugin)
        for route, handler, methods, description in (
            (f"/{PLUGIN_NAME}/voices", routes.list_voices, ["GET"], "List voices"),
            (f"/{PLUGIN_NAME}/voices/<voice_id>/audio", routes.get_audio, ["GET"], "Get voice audio"),
            (f"/{PLUGIN_NAME}/voices/upload", routes.upload_voice, ["POST"], "Upload voice"),
            (f"/{PLUGIN_NAME}/voices/upload/<keyword>", routes.upload_voice, ["POST"], "Upload voice with keyword"),
            (f"/{PLUGIN_NAME}/voices/<voice_id>", routes.delete_voice, ["DELETE"], "Delete voice"),
            (f"/{PLUGIN_NAME}/voices/<voice_id>/delete", routes.delete_voice, ["POST"], "Delete voice via Plugin Pages bridge"),
            (f"/{PLUGIN_NAME}/voices/reload", routes.reload_voices, ["POST"], "Reload voices"),
        ):
            register_web_api(route, handler, methods, description)
    except Exception as exc:
        LOGGER.warning("[AiriVoice] Plugin Pages/Web API route registration failed; WebUI is disabled: %s", exc)
        return RegistrationResult(False, False)

    return RegistrationResult(pages_registered=pages_registered, api_registered=True)
