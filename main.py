from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
import os
from typing import Dict, Optional


@register("airi_voice", "lidure", "输入文件名发送对应语音", "1.0", "https://github.com/你的仓库/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))  # 插件目录
        self.voice_dir = os.path.join(self.plugin_dir, "voices")      # 改成 voices 文件夹

        # 扫描一次 voices 目录，建立 关键词 → 完整路径 的映射
        self.voice_map: Dict[str, str] = self._scan_voices()

    def _scan_voices(self) -> Dict[str, str]:
        """扫描 voices 目录，建立 {文件名(无后缀): 绝对路径} 映射"""
        voice_map = {}
        if not os.path.exists(self.voice_dir):
            os.makedirs(self.voice_dir, exist_ok=True)
            return voice_map

        for filename in os.listdir(self.voice_dir):
            if filename.lower().endswith(('.mp3', '.wav', '.ogg', '.silk', '.amr')):
                # 去掉后缀作为关键词（strip 去空白）
                keyword = os.path.splitext(filename)[0].strip()
                full_path = os.path.join(self.voice_dir, filename)
                voice_map[keyword] = full_path
        return voice_map

    @filter.regex(r"^[\s\u3000]*([^ \u3000]+)[\s\u3000]*$")  # 匹配纯文本关键词（允许前后全角/半角空格）
    async def voice_handler(self, event: AstrMessageEvent):
        """收到消息时检查是否匹配 voices 中的文件名（无后缀）"""
        text = (event.message_str or "").strip()
        if not text:
            return  # 空消息不处理

        matched_path = self.voice_map.get(text)
        if matched_path is None:
            # 可选：如果想支持“包含”而不是“完全等于”，可以改成下面这行并注释掉 get
            # for kw, path in self.voice_map.items():
            #     if kw in text:
            #         matched_path = path
            #         break
            return  # 没匹配到就放行，不拦截

        try:
            # 发送语音
            chain = [Record.fromFileSystem(matched_path)]
            yield event.chain_result(chain)

        except Exception as e:
            yield event.plain_result(f"发送语音失败：{str(e)}（文件：{text}）")

    # 可选：加一个命令查看所有可用关键词
    @filter.command("voice_list")
    async def list_voices(self, event: AstrMessageEvent):
        if not self.voice_map:
            yield event.plain_result("voices 目录为空或没有支持的音频文件")
            return

        keywords = sorted(self.voice_map.keys())
        msg = "可用语音关键词（直接输入即可触发）：\n" + "\n".join(keywords)
        yield event.plain_result(msg)
