import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from request_parser import ParsedRequest, parse_request


def test_direct_keyword_is_preserved_with_prefix_disabled_or_enabled():
    for enable_prefix in (False, True):
        assert parse_request("晚安", enable_prefix, "direct") == ParsedRequest("keyword", "晚安")


def test_direct_random_voice_stays_available_when_prefix_is_enabled():
    assert parse_request("随机语音", True, "direct") == ParsedRequest("random_all")


def test_unprefixed_random_filter_is_ignored_when_prefix_is_enabled():
    assert parse_request("随机关键词", True, "direct") == ParsedRequest("ignore")


def test_single_slash_random_filter_uses_raw_text_and_preserves_keyword():
    assert parse_request("随机关键词", True, "direct", raw_text="/随机关键词") == ParsedRequest(
        "random_filter", "关键词"
    )


def test_double_slash_random_filter_is_ignored():
    assert parse_request("随机关键词", True, "direct", raw_text="//随机关键词") == ParsedRequest("ignore")


def test_legacy_voice_prefix_mode_extracts_keyword():
    assert parse_request("#voice 关键词", True, "prefix") == ParsedRequest("keyword", "关键词")


def test_trigger_modes_remain_distinct():
    assert parse_request("#voice 关键词", True, "direct") == ParsedRequest("keyword", "#voice 关键词")
    assert parse_request("随机语音", True, "prefix") == ParsedRequest("ignore")
    assert parse_request("晚安", True, "llm") == ParsedRequest("ignore")
