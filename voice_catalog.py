from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote


ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".silk", ".amr", ".flac", ".m4a"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
SOURCES = ("builtin", "user_added", "extra_voices")
ALIAS_STORE_FILENAME = "keyword_aliases.json"


class CatalogError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VoiceEntry:
    id: str
    name: str
    source: str
    path: Path
    extension: str
    size: int
    available: bool
    aliases: tuple[str, ...] = ()


class VoiceCatalog:
    def __init__(self, voices_root: Path, data_root: Path, extra_voice_pool: Iterable[str] = ()):
        self.roots = {
            "builtin": Path(voices_root).resolve(),
            "user_added": (Path(data_root) / "user_added").resolve(),
            "extra_voices": (Path(data_root) / "extra_voices").resolve(),
        }
        self.data_root = Path(data_root).resolve()
        self.alias_store_path = self.data_root / ALIAS_STORE_FILENAME
        self.extra_voice_pool = tuple(extra_voice_pool or ())
        self._entries: dict[str, VoiceEntry] = {}
        self._aliases: dict[str, list[str]] = {}
        self._voice_map: dict[str, str] = {}
        self._trigger_map: dict[str, str] = {}
        self.refresh()

    def set_extra_voice_pool(self, extra_voice_pool: Iterable[str]) -> None:
        self.extra_voice_pool = tuple(extra_voice_pool or ())

    def validate_keyword(self, keyword: str) -> str:
        value = (keyword or "").strip()
        if (
            not value
            or "/" in value
            or "\\" in value
            or ".." in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise CatalogError("invalid_keyword", "keyword is invalid")
        return value

    def refresh(self) -> dict[str, str]:
        entries: dict[str, VoiceEntry] = {}
        for source in SOURCES:
            root = self.roots[source]
            root.mkdir(parents=True, exist_ok=True)
            for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
                if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
                    entry = self._entry_for_path(source, path, available=True)
                    entries[entry.id] = entry

        for configured_path in self.extra_voice_pool:
            entry = self._entry_for_configured_path(configured_path)
            if entry is not None:
                entries.setdefault(entry.id, entry)

        stored_aliases = self._load_alias_store()
        pruned = {entry_id: aliases for entry_id, aliases in stored_aliases.items() if entry_id in entries}

        effective_keywords: dict[str, VoiceEntry] = {}
        for entry in sorted(entries.values(), key=lambda item: (item.name.casefold(), item.source, item.id)):
            existing = effective_keywords.get(entry.name.casefold())
            if existing is not None:
                raise CatalogError(
                    "duplicate_keyword",
                    f"duplicate effective keyword: {existing.id} and {entry.id}",
                )
            effective_keywords[entry.name.casefold()] = entry

        entries_with_aliases: dict[str, VoiceEntry] = {}
        clean_aliases: dict[str, list[str]] = {}
        for entry in sorted(entries.values(), key=lambda item: (item.name.casefold(), item.source, item.id)):
            aliases: list[str] = []
            for raw_alias in pruned.get(entry.id, []):
                alias = self.validate_keyword(raw_alias)
                folded = alias.casefold()
                existing = effective_keywords.get(folded)
                if existing is not None:
                    raise CatalogError(
                        "duplicate_keyword",
                        f"keyword '{alias}' is already used by '{existing.name}'",
                    )
                effective_keywords[folded] = entry
                aliases.append(alias)
            if aliases:
                clean_aliases[entry.id] = aliases
            entries_with_aliases[entry.id] = replace(entry, aliases=tuple(aliases))

        self._entries = entries_with_aliases
        self._aliases = clean_aliases

        voice_map: dict[str, str] = {}
        trigger_map: dict[str, str] = {}
        for source in SOURCES:
            for entry in self._sorted_entries(source=source):
                if not entry.available:
                    continue
                path = str(entry.path)
                voice_map[entry.name] = path
                trigger_map[entry.name] = path
                for alias in entry.aliases:
                    trigger_map[alias] = path
        self._voice_map = voice_map
        self._trigger_map = trigger_map

        if stored_aliases != clean_aliases:
            self._write_alias_store()
        return dict(self._voice_map)

    def trigger_map(self) -> dict[str, str]:
        return dict(self._trigger_map)

    def aliases_for(self, entry_id: str) -> list[str]:
        return list(self.resolve_entry(entry_id).aliases)

    def add_alias(self, entry_id: str, alias: str) -> VoiceEntry:
        entry = self.resolve_entry(entry_id)
        value = self.validate_keyword(alias)
        folded = value.casefold()
        for existing in self._entries.values():
            if existing.name.casefold() == folded:
                raise CatalogError(
                    "duplicate_keyword",
                    f"关键词“{value}”已被“{existing.name}”使用",
                )
            for existing_alias in existing.aliases:
                if existing_alias.casefold() == folded:
                    raise CatalogError(
                        "duplicate_keyword",
                        f"关键词“{value}”已被“{existing.name}”使用",
                    )

        aliases = list(self._aliases.get(entry.id, []))
        aliases.append(value)
        self._aliases[entry.id] = aliases
        self._write_alias_store()
        self.refresh()
        return self.resolve_entry(entry.id)

    def remove_alias(self, entry_id: str, alias: str) -> VoiceEntry:
        entry = self.resolve_entry(entry_id)
        value = self.validate_keyword(alias)
        aliases = list(self._aliases.get(entry.id, []))
        match_index = next(
            (index for index, existing in enumerate(aliases) if existing.casefold() == value.casefold()),
            None,
        )
        if match_index is None:
            raise CatalogError("not_found", "keyword alias was not found")
        aliases.pop(match_index)
        if aliases:
            self._aliases[entry.id] = aliases
        else:
            self._aliases.pop(entry.id, None)
        self._write_alias_store()
        self.refresh()
        return self.resolve_entry(entry.id)

    def list_entries(self, query: str = "", source: str | None = None) -> list[VoiceEntry]:
        if source is not None and source not in SOURCES:
            raise CatalogError("invalid_source", "source is invalid")
        query_folded = (query or "").casefold()
        return [
            entry
            for entry in self._sorted_entries(source=source)
            if query_folded in entry.name.casefold()
        ]

    def save_upload(self, filename: str, keyword: str, data: bytes) -> VoiceEntry:
        return self._save_file("extra_voices", filename, keyword, data)

    def save_user_upload(self, filename: str, keyword: str, data: bytes) -> VoiceEntry:
        return self._save_file("user_added", filename, keyword, data)

    def delete(self, entry_id: str) -> None:
        entry = self.resolve_entry(entry_id)
        if entry.id.startswith("extra_voices:configured/"):
            raise CatalogError("read_only", "configured voice pool entries cannot be deleted")
        if not entry.available:
            raise CatalogError("not_found", "voice entry does not exist")
        entry.path.unlink()
        if self._aliases.pop(entry.id, None) is not None:
            self._write_alias_store()
        self.refresh()

    def resolve_entry(self, entry_id: str) -> VoiceEntry:
        normalized_id = unquote(entry_id) if isinstance(entry_id, str) else entry_id
        entry = self._entries.get(normalized_id)
        if entry is None:
            raise CatalogError("not_found", "voice entry was not found")
        return entry

    def audio_path(self, entry_id: str) -> Path:
        entry = self.resolve_entry(entry_id)
        if not entry.available:
            raise CatalogError("not_found", "voice file was not found")
        return entry.path

    def _save_file(self, source: str, filename: str, keyword: str, data: bytes) -> VoiceEntry:
        if not isinstance(data, bytes):
            raise CatalogError("invalid_upload", "upload data must be bytes")
        if len(data) > MAX_UPLOAD_BYTES:
            raise CatalogError("too_large", "upload exceeds 50 MB")
        if "/" in filename or "\\" in filename:
            raise CatalogError("invalid_filename", "filename is invalid")
        extension = Path(filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise CatalogError("invalid_extension", "file extension is not allowed")
        name = self.validate_keyword(keyword)
        folded = name.casefold()
        for entry in self._entries.values():
            if entry.name.casefold() == folded or any(alias.casefold() == folded for alias in entry.aliases):
                raise CatalogError("duplicate_keyword", "voice keyword already exists")
        path = self.roots[source] / f"{name}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.refresh()
        return self.resolve_entry(self._entry_id(source, path.relative_to(self.roots[source])))

    def _load_alias_store(self) -> dict[str, list[str]]:
        if not self.alias_store_path.is_file():
            return {}
        try:
            payload = json.loads(self.alias_store_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError("invalid_alias_store", "keyword alias store is invalid") from exc
        if not isinstance(payload, dict):
            raise CatalogError("invalid_alias_store", "keyword alias store is invalid")
        result: dict[str, list[str]] = {}
        for entry_id, aliases in payload.items():
            if not isinstance(entry_id, str) or not isinstance(aliases, list):
                raise CatalogError("invalid_alias_store", "keyword alias store is invalid")
            if any(not isinstance(alias, str) for alias in aliases):
                raise CatalogError("invalid_alias_store", "keyword alias store is invalid")
            if aliases:
                result[entry_id] = list(aliases)
        return result

    def _write_alias_store(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        payload = {
            entry_id: list(aliases)
            for entry_id, aliases in sorted(self._aliases.items())
            if aliases
        }
        temporary = self.alias_store_path.with_suffix(self.alias_store_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.alias_store_path)

    def _entry_for_configured_path(self, configured_path: str) -> VoiceEntry | None:
        if not isinstance(configured_path, str) or not configured_path.strip():
            return None
        raw_path = Path(configured_path.strip())
        candidate = (raw_path if raw_path.is_absolute() else self.data_root / raw_path).resolve()
        try:
            relative = candidate.relative_to(self.data_root)
        except ValueError:
            return None
        if candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
            return None
        available = candidate.is_file()
        return VoiceEntry(
            id=self._entry_id("extra_voices", Path("configured") / relative),
            name=candidate.stem.strip(),
            source="extra_voices",
            path=candidate,
            extension=candidate.suffix.lower(),
            size=candidate.stat().st_size if available else 0,
            available=available,
        )

    def _entry_for_path(self, source: str, path: Path, available: bool) -> VoiceEntry:
        root = self.roots[source]
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise CatalogError("invalid_path", "voice path is outside its root") from exc
        return VoiceEntry(
            id=self._entry_id(source, relative),
            name=path.stem.strip(),
            source=source,
            path=resolved,
            extension=path.suffix.lower(),
            size=resolved.stat().st_size if available else 0,
            available=available,
        )

    def _sorted_entries(self, source: str | None = None) -> list[VoiceEntry]:
        return sorted(
            (entry for entry in self._entries.values() if source is None or entry.source == source),
            key=lambda entry: (entry.name.casefold(), entry.name, entry.source, entry.id),
        )

    @staticmethod
    def _entry_id(source: str, relative: Path) -> str:
        return f"{source}:{relative.as_posix()}"
