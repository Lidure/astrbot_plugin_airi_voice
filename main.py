from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from astrbot.core.star.star_tools import StarTools
from pathlib import Path
import os
from typing import Dict, Optional

@register("airi_voice", "lidure", "输入文件名发送对应语音（支持本地 + 网页上传）", "1.1", "https://github.com/你的用户名/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        
        # 插件目录 + 本地 voices 文件夹
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))
        self.voice_dir = os.path.join(self.plugin_dir, "voices")
        
        # 获取 AstrBot 为本插件分配的专用数据目录（模仿 pokepro）
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_airi_voice")
        self.extra_voice_dir = self.data_dir / "extra_voices"
        self.extra_voice_dir.mkdir(parents=True, exist_ok=True)
        
        # 语音映射：关键词（文件名无后缀） → 绝对路径
        self.voice_map: Dict[str, str] = {}
        
        # 加载本地 voices/
        self._load_local_voices()
        
        # 保存 config 用于 reload
        self.config = config
        
        # 加载网页配置的额外语音
        self._load_web_voices(config)
        
        logger.info(f"[AiriVoice] 初始化完成，当前语音总数：{len(self.voice_map)} 个")

    def _load_local_voices(self):
        """扫描本地 voices/ 文件夹"""
        if not os.path.exists(self.voice_dir):
            os.makedirs(self.voice_dir, exist_ok=True)
            logger.info("[AiriVoice] 已创建本地 voices 目录")

        count = 0
        for file in os.listdir(self.voice_dir):
            if file.lower().endswith(('.mp3', '.wav', '.ogg', '.silk', '.amr')):
                keyword = os.path.splitext(file)[0].strip()
                abs_path = os.path.join(self.voice_dir, file)
                self.voice_map[keyword] = abs_path
                count += 1
                logger.debug(f"[AiriVoice] 本地加载：'{keyword}' → {abs_path}")
        
        if count > 0:
            logger.info(f"[AiriVoice] 从本地 voices 加载 {count} 个语音")

    def _load_web_voices(self, config: dict = None):
        """从网页配置加载额外语音（相对路径拼接）"""
        if config is None:
            logger.info("[AiriVoice] 未收到 config，不加载网页语音")
            return
        
        extra_pool = config.get("extra_voice_pool", [])
        if not extra_pool:
            logger.info("[AiriVoice] 无 extra_voice_pool 配置")
            return
        
        logger.info(f"[AiriVoice] 网页相对路径池：{extra_pool}")
        
        loaded = 0
        for rel_path in extra_pool:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            
            abs_path = self.data_dir / rel_path
            logger.debug(f"[AiriVoice] 检查网页路径：{abs_path}")
            
            if abs_path.exists() and abs_path.is_file():
                keyword = os.path.splitext(os.path.basename(rel_path))[0].strip()
                if keyword:
                    self.voice_map[keyword] = str(abs_path)
                    loaded += 1
                    logger.info(f"[AiriVoice] 网页加载成功：'{keyword}' → {abs_path}")
            else:
                logger.warning(f"[AiriVoice] 网页文件不存在：{abs_path} (相对: {rel_path})")
        
        if loaded > 0:
            logger.info(f"[AiriVoice] 从网页配置加载 {loaded} 个额外语音")

    @filter.regex(r"^\s*([^\s\u3000]+)\s*$")  # 匹配纯关键词（前后允许空白）
    async def voice_handler(self, event: AstrMessageEvent):
        text = (event.message_str or "").strip()
        if not text:
            return

        matched_path = self.voice_map.get(text)
        if matched_path is None:
            return  # 未匹配，放行

        try:
            logger.info(f"[AiriVoice] 触发语音：'{text}' → {matched_path}")
            chain = [Record.fromFileSystem(matched_path)]
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"[AiriVoice] 发送失败 '{text}': {str(e)}", exc_info=True)
            yield event.plain_result(f"语音发送失败：{str(e)}")

    @filter.command("voice_reload")
    async def reload_voices(self, event: AstrMessageEvent):
        old_count = len(self.voice_map)
        
        # 重新加载本地
        self.voice_map = {}
        self._load_local_voices()
        
        # 重新加载网页配置
        if self.config:
            self._load_web_voices(self.config)
        
        new_count = len(self.voice_map)
        yield event.plain_result(
            f"语音列表已刷新！\n"
            f"之前 {old_count} 个 → 现在 {new_count} 个\n"
            f"网页上传的文件已重新加载"
        )

    @filter.command("voice_list")
    async def list_voices(self, event: AstrMessageEvent):
        if not self.voice_map:
            yield event.plain_result("当前没有可用语音～快去 voices/ 或网页配置添加吧！")
            return

        keys = sorted(self.voice_map.keys())
        msg = f"可用关键词（共 {len(keys)} 个）：\n" + "\n".join(f"・ {k}" for k in keys[:50])
        if len(keys) > 50:
            msg += f"\n... 还有 {len(keys)-50} 个未显示"
        msg += "\n\n直接输入关键词即可触发语音～"
        yield event.plain_result(msg)
