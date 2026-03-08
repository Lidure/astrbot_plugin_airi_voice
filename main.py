from pathlib import Path
from typing import Dict

# 核心导入（固定路径）
from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.message_components import Record
from astrbot.api import logger

class VoiceDaka(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.voice_dir = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, str] = {}  # 关键词 → 绝对路径

        self._load_voices()

    def _load_voices(self):
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("已创建 voices 目录，请放入 .wav / .silk 等音频文件")
            return

        count = 0
        for file in self.voice_dir.iterdir():
            if file.is_file() and file.suffix.lower() in {".silk", ".amr", ".ogg", ".mp3", ".wav"}:
                keyword = file.stem.strip()
                self.voice_map[keyword] = str(file.absolute())
                count += 1

        if count > 0:
            logger.info(f"语音打卡包加载完成：{count} 个语音文件可用")
        else:
            logger.warning("voices 目录为空或无有效音频文件")

    # 方式1：如果你想用装饰器（但只支持 command，不支持纯 keyword）
    # @filter.command("打卡啦摩托")  # ← 如果只支持少数固定词，可以这样写多个
    # async def on_command_daka(self, event: AstrMessageEvent):
    #     await self._send_voice(event, "打卡啦摩托")

    # 方式2：推荐 - 不依赖装饰器，手动在通用消息处理器里匹配（最稳）
    async def on_message(self, event: AstrMessageEvent):
        # 获取纯文本（去前后空白）
        text = event.message_str.strip()
        if not text:
            return False  # 不处理空消息

        matched_path = self.voice_map.get(text)
        if matched_path is None:
            return False  # 没匹配，放行给其他插件/核心逻辑

        # 匹配到了 → 发送语音
        try:
            chain = MessageChain()
            chain.append(Record(file=matched_path))  # 本地绝对路径

            # 发送回复（用 reply 带引用更好）
            await event.reply(chain)
            logger.debug(f"已发送语音：{text} → {matched_path}")

            return True  # 已处理，阻止继续向下传播

        except Exception as e:
            logger.error(f"语音发送失败（关键词：{text}）：{str(e)}", exc_info=True)
            # 可选：友好提示用户
            await event.reply(f"语音加载失败了… ({str(e)})")
            return True
