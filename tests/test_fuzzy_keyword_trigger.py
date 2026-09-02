import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import request_parser
from request_parser import ParsedRequest, parse_request


def match_trigger_keyword(text, keys, fuzzy_match):
    matcher = getattr(request_parser, "match_trigger_keyword", None)
    assert callable(matcher), "request_parser.match_trigger_keyword is not implemented"
    return matcher(text, keys, fuzzy_match=fuzzy_match)


def test_fuzzy_match_disabled_keeps_exact_keyword_contract():
    keys = ["打卡", "桃井爱莉"]

    assert match_trigger_keyword("打卡", keys, fuzzy_match=False) == "打卡"
    assert match_trigger_keyword("今天来打卡一下", keys, fuzzy_match=False) is None


def test_fuzzy_match_accepts_keyword_inside_sentence_for_primary_or_alias():
    keys = ["打卡啦摩托", "打卡", "上班啦"]

    assert match_trigger_keyword("今天也来打卡一下吧", keys, fuzzy_match=True) == "打卡"
    assert match_trigger_keyword("好啦，上班啦各位", keys, fuzzy_match=True) == "上班啦"


def test_fuzzy_match_prefers_exact_match_then_longest_contained_keyword():
    keys = ["爱莉", "桃井爱莉", "打卡"]

    assert match_trigger_keyword("爱莉", keys, fuzzy_match=True) == "爱莉"
    assert match_trigger_keyword("今天桃井爱莉来打卡", keys, fuzzy_match=True) == "桃井爱莉"


def test_prefix_mode_still_requires_prefix_but_can_fuzzy_match_payload():
    keys = ["打卡"]

    prefixed = parse_request("#voice 今天来打卡一下", False, "prefix")
    plain = parse_request("今天来打卡一下", False, "prefix")

    assert prefixed == ParsedRequest("keyword", "今天来打卡一下")
    assert match_trigger_keyword(prefixed.keyword or "", keys, fuzzy_match=True) == "打卡"
    assert plain == ParsedRequest("ignore")


def test_llm_and_random_parser_contracts_remain_outside_fuzzy_keyword_matching():
    assert parse_request("今天来打卡一下", False, "llm") == ParsedRequest("ignore")
    assert parse_request("随机语音", False, "direct") == ParsedRequest("random_all")
    assert parse_request("随机打卡", False, "direct") == ParsedRequest("random_filter", "打卡")


def test_fuzzy_match_config_defaults_off_and_main_wires_it_into_keyword_resolution():
    schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
    main = Path("main.py").read_text(encoding="utf-8")

    assert schema["fuzzy_keyword_match"]["type"] == "bool"
    assert schema["fuzzy_keyword_match"]["default"] is False
    assert 'self.fuzzy_keyword_match = bool(self.config.get("fuzzy_keyword_match", False))' in main
    assert "match_trigger_keyword(request.keyword or \"\", self.voice_map.keys(), self.fuzzy_keyword_match)" in main
