import os
from pathlib import Path
from typing import Dict

from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api import logger  # 可选，用于错误日志

from astrbot.message.message_chain import MessageChain
from astrbot.message.segment import Record

class VoiceDaka(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 插件目录下的 voices 文件夹
        self.voice_dir = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, str] = {}  # 关键词 -> 文件路径

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

    @filter.keyword()  # 使用关键词匹配装饰器
    async def on_message(self, event: AstrMessageEvent):
        text = event.message_str.strip()

        if not text:
            return False

        matched_path = self.voice_map.get(text)
        if not matched_path:
            return False  # 没匹配到，放行给其他插件

        try:
            chain = MessageChain()
            chain.append(Record(file=matched_path))  # 发送本地语音文件

            await event.reply(chain)
            return True  # 已处理，拦截后续

        except Exception as e:
            logger.error(f"发送语音失败: {e}")
            await event.reply(f"语音发送出错了: {str(e)}")
            return True
