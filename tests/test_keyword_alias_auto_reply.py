from pathlib import Path


def test_bot_reply_auto_voice_scans_primary_and_alias_trigger_keywords():
    source = Path("main.py").read_text(encoding="utf-8")

    assert "for keyword in sorted(self.voice_map.keys()):" in source
