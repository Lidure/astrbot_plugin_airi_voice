from pathlib import Path


def test_aliases_do_not_inflate_reported_voice_counts():
    source = Path("main.py").read_text(encoding="utf-8")

    assert '初始化完成，共 {len(self.primary_voice_map)} 个语音' in source
    assert '已重新加载，共 {len(self.primary_voice_map)} 个语音' in source
    assert '初始化完成，共 {len(self.voice_map)} 个语音' not in source
    assert '已重新加载，共 {len(self.voice_map)} 个语音' not in source
