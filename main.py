from pathlib import Path
from typing import Dict

# 核心导入（最新路径）
from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.message_components import Record   # ← 这里导入 Record
from astrbot.api import logger                      # 用于错误日志

class VoiceDaka(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 插件目录下的 voices 文件夹
        self.voice_dir = Path(__file__).parent / "voices"
        self.voice_map: Dict[str, str] = {}  # 关键词 → 完整文件路径

        self._load_voices()

    def _load_voices(self):
        """扫描 voices/ 目录，把文件名（去掉后缀）作为触发关键词"""
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("已创建 voices 目录，等待放置音频文件")
            return

        loaded_count = 0
        for file in self.voice_dir.iterdir():
            if file.is_file() and file.suffix.lower() in {".silk", ".amr", ".ogg", ".mp3", ".wav"}:
                keyword = file.stem.strip()  # 文件名（无后缀）作为关键词
                self.voice_map[keyword] = str(file.absolute())  # 用绝对路径更稳
                loaded_count += 1

        logger.info(f"语音打卡包：成功加载 {loaded_count} 个语音文件")

    @filter.keyword()  # 关键词匹配（全消息文本匹配）
    async def on_message(self, event: AstrMessageEvent):
        text = event.message_str.strip()
        if not text:
            return False  # 空消息不处理

        matched_path = self.voice_map.get(text)
        if not matched_path:
            return False  # 未匹配到关键词，放行给其他插件

        try:
            chain = MessageChain()
            # 发送本地文件作为语音（目前官方示例推荐 wav 格式最兼容）
            # 如果你的文件不是 wav，建议提前转换，否则部分平台可能不播放
            chain.append(Record(file=matched_path))

            await event.reply(chain)
            logger.debug(f"成功发送语音：{text} → {matched_path}")
            return True  # 已处理，拦截后续插件

        except Exception as e:
            logger.error(f"发送语音失败（关键词：{text}）：{str(e)}", exc_info=True)
            # 可选：给用户友好提示
            await event.reply(f"语音出错了... ({str(e)})")
            return True  # 还是拦截，避免重复报错
