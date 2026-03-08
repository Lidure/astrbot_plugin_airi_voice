# main.py
from pathlib import Path
from typing import Dict, Optional

from astrbot.api.star import Context, Star
from astrbot.api.event import filter, AstrMessageEvent, EventMessageType
from astrbot.api.message_components import Record
from astrbot.api import logger

class VoiceKeywordPlayer(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 插件目录下的 voices 文件夹
        self.voice_dir: Path = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, Path] = {}  # 关键词（文件名无后缀） → 完整 Path 对象

        self._scan_voices()

    def _scan_voices(self):
        """扫描 voices 文件夹，建立 关键词 → 文件路径 映射"""
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[VoiceKeyword] 已创建 voices 目录，请放入音频文件后重载插件")
            return

        self.voice_map.clear()
        count = 0
        for file in self.voice_dir.iterdir():
            if file.is_file():
                ext = file.suffix.lower()
                if ext in {".mp3", ".wav", ".silk", ".amr", ".ogg"}:
                    keyword = file.stem.strip()  # 文件名去后缀作为关键词
                    self.voice_map[keyword] = file
                    count += 1
                    logger.debug(f"[VoiceKeyword] 加载: '{keyword}' → {file}")

        if count > 0:
            logger.info(f"[VoiceKeyword] 加载完成：{count} 个音频文件")
            logger.info(f"[VoiceKeyword] 支持关键词：{', '.join(sorted(self.voice_map.keys()))}")
        else:
            logger.warning("[VoiceKeyword] voices 目录中没有支持的音频文件")

    # 监听所有消息，然后在里面做精确匹配（最稳妥的方式，避免装饰器兼容问题）
    @filter.event_message_type(EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        if not event.message_str:
            return

        text = event.message_str.strip()

        # 精确匹配：用户输入必须完全等于文件名（去后缀）
        file_path = self.voice_map.get(text)
        if file_path is None:
            return  # 没匹配到就什么都不做，放行给其他插件

        try:
            logger.info(f"[VoiceKeyword] 匹配成功：'{text}' → {file_path}")

            # 构建消息链 → 发送语音
            chain = [Record.fromFileSystem(str(file_path))]

            # 使用 yield 方式返回结果（兼容你原代码的风格）
            yield event.chain_result(chain)

            # 如果你的版本更喜欢 await 风格，可以改成：
            # await event.reply_chain(chain)
            # 但 yield 是许多插件常用的

        except Exception as e:
            logger.error(f"[VoiceKeyword] 发送语音失败 '{text}': {str(e)}", exc_info=True)
            yield event.plain_result(f"语音发送失败：{str(e)}（建议将文件转为 .wav 格式）")

    # 可选：插件重载时重新扫描（如果用户中途添加文件）
    async def on_plugin_reload(self):
        self._scan_voices()
        yield "语音关键词列表已刷新"
