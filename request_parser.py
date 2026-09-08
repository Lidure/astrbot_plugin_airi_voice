from dataclasses import dataclass
import inspect


@dataclass(frozen=True)
class ParsedRequest:
    kind: str
    keyword: str | None = None


_RANDOM_DISPATCH_ATTR = "__airi_random_voice_dispatched__"
_RANDOM_ALL_PHRASES = {"随机语音", "随机发条语音"}


def claim_random_dispatch(event: object) -> bool:
    """Claim random-voice handling once for one AstrBot event."""
    if event is None:
        return False
    try:
        if getattr(event, _RANDOM_DISPATCH_ATTR, False):
            return False
        setattr(event, _RANDOM_DISPATCH_ATTR, True)
    except Exception:
        return True
    return True


def _resolve_case_insensitive(value: bool | None) -> bool:
    if value is not None:
        return bool(value)
    try:
        frame = inspect.currentframe()
        caller_self = frame.f_back.f_back.f_locals.get("self") if frame and frame.f_back and frame.f_back.f_back else None
        config = getattr(caller_self, "config", None)
        if isinstance(config, dict):
            return bool(config.get("case_insensitive_keyword_match", False))
    except Exception:
        pass
    return False


def match_trigger_keyword(
    text: str,
    voice_keys,
    fuzzy_match: bool = False,
    case_insensitive: bool | None = None,
) -> str | None:
    """Resolve an exact or contained trigger keyword deterministically."""
    value = (text or "").strip()
    keys = [key for key in voice_keys if isinstance(key, str) and key]
    case_insensitive = _resolve_case_insensitive(case_insensitive)

    if case_insensitive:
        value_key = value.casefold()
        exact = next((key for key in keys if key.casefold() == value_key), None)
        if exact is not None:
            return exact
    elif value in keys:
        return value

    if not fuzzy_match or not value:
        return None

    if case_insensitive:
        value_key = value.casefold()
        matches = [key for key in keys if key.casefold() in value_key]
    else:
        matches = [key for key in keys if key in value]
    if not matches:
        return None
    matches.sort(
        key=lambda key: (
            -len(key),
            value.casefold().find(key.casefold()) if case_insensitive else value.find(key),
            key,
        )
    )
    return matches[0]


def parse_request(
    text: str,
    enable_prefix: bool,
    trigger_mode: str,
    raw_text: str | None = None,
    known_keywords=None,
) -> ParsedRequest:
    text = (text or "").strip()
    raw = raw_text.strip() if isinstance(raw_text, str) else None
    command_text = raw if raw is not None else text

    if command_text.startswith("/voice."):
        return ParsedRequest("admin_command")
    if trigger_mode == "llm" or not text:
        return ParsedRequest("ignore")
    if trigger_mode == "prefix":
        if text.lower().startswith("#voice "):
            keyword = text[7:].strip()
            return ParsedRequest("keyword", keyword) if keyword else ParsedRequest("ignore")
        return ParsedRequest("ignore")

    if enable_prefix and raw is not None and raw.startswith("//随机"):
        return ParsedRequest("ignore")

    random_text = raw[1:].strip() if raw is not None and raw.startswith("/随机") else text
    has_single_prefix = raw is not None and raw.startswith("/随机")

    if random_text in _RANDOM_ALL_PHRASES:
        if enable_prefix and random_text != "随机语音" and not has_single_prefix:
            return ParsedRequest("ignore")
        return ParsedRequest("random_all")

    if has_single_prefix and random_text.startswith("随机"):
        keyword = random_text[2:].strip()
        return ParsedRequest("random_filter", keyword) if keyword else ParsedRequest("random_all")

    known = {item for item in (known_keywords or ()) if isinstance(item, str) and item}
    if text in known:
        return ParsedRequest("keyword", text)

    if random_text.startswith("随机"):
        keyword = random_text[2:].strip()
        if enable_prefix and not has_single_prefix:
            return ParsedRequest("ignore")
        return ParsedRequest("random_filter", keyword) if keyword else ParsedRequest("random_all")
    return ParsedRequest("keyword", text)
