from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
import os
from typing import Dict, Optional
from pathlib import Path
from astrbot.api import logger 

@register("airi_voice", "lidure", "输入文件名发送对应语音", "1.0", "https://github.com/你的仓库/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
            super().__init__(context)
            self.plugin_dir = os.path.abspath(os.path.dirname(__file__))
            self.voice_dir = os.path.join(self.plugin_dir, "voices")
            self.voice_map: Dict[str, str] = self._scan_voices()
    
            logger.info("[AiriVoice] === 配置加载开始 ===")
            if config is not None:
                logger.info(f"[AiriVoice] 完整 config: {config}")
                extra = config.get("extra_voice_file")
                if extra:
                    # 处理 list（即使单个文件也可能是 list）
                    if isinstance(extra, list):
                        for rel_path in extra:
                            if isinstance(rel_path, str):
                                # 构建绝对路径：假设上传文件在 data/config/插件名/ 下
                                # 插件名从 __file__ 或硬编码（这里假设 'astrbot_plugin_airi_voice'）
                                plugin_name = "astrbot_plugin_airi_voice"
                                config_base = Path(__file__).parent.parent.parent / "data" / "config" / plugin_name
                                abs_path = config_base / rel_path
    
                                if abs_path.exists():
                                    keyword = os.path.splitext(os.path.basename(rel_path))[0].strip()
                                    self.voice_map[keyword] = str(abs_path)
                                    logger.info(f"[AiriVoice] 从网页上传加载: '{keyword}' → {abs_path}")
                                else:
                                    logger.error(f"[AiriVoice] 上传文件路径不存在: {abs_path} (相对: {rel_path})")
                    elif isinstance(extra, str):
                        # fallback 如果是 str
                        # 同上构建路径...
                        pass  # 可类似处理
                    else:
                        logger.warning(f"[AiriVoice] extra_voice_file 未知格式: {type(extra)}")
                else:
                    logger.info("[AiriVoice] 无 extra_voice_file")
            else:
                logger.info("[AiriVoice] 未收到 config")
    
            logger.info(f"[AiriVoice] 当前语音总数: {len(self.voice_map)} 个")
            logger.info("[AiriVoice] === 配置加载结束 ===")
    

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

    @filter.regex(r"^\s*([^\s\u3000]+)\s*$")  # 匹配纯文本关键词（允许前后全角/半角空格）
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



    @filter.command("voice_reload")
    async def reload_voices(self, event: AstrMessageEvent):
        old_count = len(self.voice_map)
    
        # 重新扫描本地
        self.voice_map = self._scan_voices()
    
        # 重新加载 config 中的上传文件（复用 __init__ 逻辑）
        if hasattr(self, 'config') and self.config:
            extra = self.config.get("extra_voice_file")
            if isinstance(extra, list):
                for rel_path in extra:
                    if isinstance(rel_path, str):
                        plugin_name = "astrbot_plugin_airi_voice"
                        config_base = Path(__file__).parent.parent.parent / "data" / "config" / plugin_name
                        abs_path = config_base / rel_path
                        if abs_path.exists():
                            keyword = os.path.splitext(os.path.basename(rel_path))[0].strip()
                            self.voice_map[keyword] = str(abs_path)  # 会覆盖同名，但正常
    
        new_count = len(self.voice_map)
        yield event.plain_result(
            f"已刷新语音列表！\n"
            f"总数：{old_count} → {new_count}（含网页上传文件）\n"
            f"试试输入关键词（如 愛♡）测试～"
        )
        
    # 可选：加一个命令查看所有可用关键词
    @filter.command("voice_list")
    async def list_voices(self, event: AstrMessageEvent):
        if not self.voice_map:
            yield event.plain_result("voices 目录为空哦～快去添加语音文件吧！")
            return

        args = (event.message_str or "").strip().split()
        page = 1
        if len(args) > 1 and args[1].isdigit():
            page = int(args[1])

        keys = sorted(self.voice_map.keys())
        total = len(keys)
        page_size = 20
        start = (page - 1) * page_size
        end = start + page_size

        if start >= total:
            yield event.plain_result(f"页码过大啦～总共只有 {total} 个语音（共 {((total-1)//page_size)+1} 页）")
            return

        page_keys = keys[start:end]
        msg = f"可用语音关键词（第 {page} 页，共 {total} 个，前 {len(page_keys)} 个）：\n"
        msg += "\n".join(f"・ {k}" for k in page_keys)
        msg += f"\n\n输入 /voice_list {page+1} 查看下一页～"

        yield event.plain_result(msg)
