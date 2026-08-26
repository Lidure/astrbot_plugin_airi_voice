from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedRequest:
    kind: str
    keyword: str | None = None


_RANDOM_DISPATCH_ATTR = "__airi_random_voice_dispatched__"


def claim_random_dispatch(event: object) -> bool:
    """Claim random-voice handling once for one AstrBot event.

    Multiple AstrBot filters can match the same /随机... message. The check and
    assignment are intentionally synchronous so only the first matching handler
    owns the send before any handler reaches an await/yield boundary.
    """

    if event is None:
        return False
    try:
        if getattr(event, _RANDOM_DISPATCH_ATTR, False):
            return False
        setattr(event, _RANDOM_DISPATCH_ATTR, True)
    except Exception:
        # Preserve legacy behavior for unusual immutable event proxies.
        return True
    return True


def parse_request(text: str, enable_prefix: bool, trigger_mode: str, raw_text: str | None = None) -> ParsedRequest:
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
    if random_text in {"随机语音", "随机发条语音"}:
        if enable_prefix and random_text != "随机语音" and not has_single_prefix:
            return ParsedRequest("ignore")
        return ParsedRequest("random_all")
    if random_text.startswith("随机"):
        keyword = random_text[2:].strip()
        if enable_prefix and not has_single_prefix:
            return ParsedRequest("ignore")
        return ParsedRequest("random_filter", keyword) if keyword else ParsedRequest("random_all")
    return ParsedRequest("keyword", text)
