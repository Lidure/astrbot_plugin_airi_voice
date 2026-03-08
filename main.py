import os
from pathlib import Path
from typing import Dict

from astrbot.star import Context, register
from astrbot.message.message_event import AstrMessageEvent
from astrbot.message.message_chain import MessageChain
from astrbot.message.segment import Record
from astrbot.star.filter import command, on_keyword

@register("语音打卡包", "Lidure", "输入关键词发送对应语音", "1.0", "https://github.com/Lidure/astrbot_plugin_airi_voice")
class VoiceDaka:
    def __init__(self, context: Context):
        self.context = context
        # 插件目录下的 voices 文件夹
        self.voice_dir = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, str] = {}  # 关键词 -> 文件名（不含后缀）

        self._load_voices()

    def _load_voices(self):
        """扫描 voices/ 目录，文件名（去掉后缀）作为触发词"""
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            return

        for file in self.voice_dir.iterdir():
            if file.is_file() and file.suffix.lower() in {".silk", ".amr", ".ogg", ".mp3", ".wav"}:
                keyword = file.stem.strip()   # 文件名作为关键词
                self.voice_map[keyword] = str(file)

    @on_keyword()
    async def handle_keyword(self, event: AstrMessageEvent):
        text = event.message_str.strip()

        if not text:
            return False

        matched_path = self.voice_map.get(text)
        if not matched_path:
            # 也可以做模糊匹配或 startsWith，但先简单精确匹配
            return False

        chain = MessageChain()
        # 核心：发送 Record 语音段
        chain.append(Record(file=matched_path))  # 本地绝对路径

        # 如果你的平台不支持本地路径，可以改用 file_url=http链接（需自己搭文件服务器）

        await event.reply(chain)
        return True   # 拦截，不让继续处理
