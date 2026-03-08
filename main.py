from pathlib import Path
from typing import Dict, Optional

from astrbot.api.star import Context, Star
from astrbot.api.event import (
    AstrMessageEvent,
    MessageChain,
    filter,                  # 必须导入
    EventMessageType         # 枚举类型在这里
)
from astrbot.api.message_components import Record
from astrbot.api import logger

class VoiceDaka(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.voice_dir = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, str] = {}
        self._load_voices()

    def _load_voices(self):
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[VoiceDaka] 已创建 voices 目录，放入音频文件后重载插件")
            return

        count = 0
        for file in self.voice_dir.iterdir():
            if file.is_file():
                ext = file.suffix.lower()
                if ext in {".silk", ".amr", ".ogg", ".mp3", ".wav"}:
                    keyword = file.stem.strip()
                    abs_path = str(file.absolute())
                    self.voice_map[keyword] = abs_path
                    count += 1
                    logger.debug(f"[VoiceDaka] 加载语音: '{keyword}' → {abs_path} ({ext})")

        if count > 0:
            logger.info(f"[VoiceDaka] 加载完成：{count} 个语音文件")
            logger.info(f"[VoiceDaka] 可用关键词: {', '.join(sorted(self.voice_map.keys()))}")
        else:
            logger.warning("[VoiceDaka] voices 目录中没有支持的音频文件")

    # 关键：使用 @filter.event_message_type 注册监听所有消息
    @filter.event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        # 方法名可以自定义，但建议带 on_ 前缀表示事件处理器
        if event.message_str is None:
            logger.debug("[VoiceDaka] 消息无文本内容，跳过")
            return False

        text = event.message_str.strip()
        logger.debug(f"[VoiceDaka] 收到消息: '{text}' (原始: '{event.message_str}')")

        if not text:
            return False

        matched_path: Optional[str] = self.voice_map.get(text)

        # 如果严格匹配失败，尝试“消息中包含关键词”（更宽容）
        if matched_path is None:
            for kw, path in self.voice_map.items():
                if kw in text:
                    matched_path = path
                    logger.debug(f"[VoiceDaka] 包含匹配: '{kw}' 在 '{text}' 中")
                    break

        if matched_path is None:
            logger.debug(f"[VoiceDaka] 未匹配关键词: '{text}'")
            return False

        try:
            logger.info(f"[VoiceDaka] 尝试发送语音: '{text}' → {matched_path}")
            chain = MessageChain()
            chain.append(Record(file=matched_path))
            await event.reply(chain)
            logger.info("[VoiceDaka] 语音发送成功")
            return True  # 处理完成，拦截后续插件

        except Exception as e:
            logger.error(f"[VoiceDaka] 发送语音失败: {str(e)}", exc_info=True)
            await event.reply(f"语音发送失败（可能是格式问题，建议用 .wav）：{str(e)}")
            return True
