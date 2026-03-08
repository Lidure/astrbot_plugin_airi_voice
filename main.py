from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
import os
from typing import Dict, Optional
from astrbot.api import logger 

@register("airi_voice", "lidure", "输入文件名发送对应语音", "1.0", "https://github.com/你的仓库/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.plugin_dir = os.path.abspath(os.path.dirname(__file__))
        self.voice_dir = os.path.join(self.plugin_dir, "voices")
        self.voice_map: Dict[str, str] = self._scan_voices()
    
        logger.info("[AiriVoice] === 插件配置加载开始 ===")
        if config is not None:
            logger.info(f"[AiriVoice] 收到的 config 完整内容: {config}")
            extra_file = config.get("extra_voice_file")
            if extra_file:
                logger.info(f"[AiriVoice] extra_voice_file 值: {extra_file} (类型: {type(extra_file)})")
                
                # 尝试处理不同可能格式
                file_path = None
                if isinstance(extra_file, str):
                    file_path = extra_file
                elif isinstance(extra_file, dict) and "path" in extra_file:
                    file_path = extra_file["path"]
                else:
                    logger.warning("[AiriVoice] extra_voice_file 格式未知，无法加载")
                
                if file_path:
                    if os.path.exists(file_path):
                        keyword = os.path.splitext(os.path.basename(file_path))[0].strip()
                        self.voice_map[keyword] = file_path
                        logger.info(f"[AiriVoice] 成功从网页配置加载额外语音: '{keyword}' → {file_path}")
                    else:
                        logger.error(f"[AiriVoice] 上传文件路径不存在！路径: {file_path}")
            else:
                logger.info("[AiriVoice] 无 extra_voice_file 配置")
        else:
            logger.info("[AiriVoice] __init__ 未收到 config 参数")
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
    
    # 重新扫描本地 voices/
    self.voice_map = self._scan_voices()
    
    # 重新加载网页 config（需要访问 config，但 __init__ 外的 reload 无法直接拿 config）
    # 临时方案：假设你把 config 存为 self.config
    if hasattr(self, 'config') and self.config:
        extra_file = self.config.get("extra_voice_file")
        if extra_file and isinstance(extra_file, str) and os.path.exists(extra_file):
            keyword = os.path.splitext(os.path.basename(extra_file))[0].strip()
            self.voice_map[keyword] = extra_file
    
    new_count = len(self.voice_map)
    yield event.plain_result(
        f"语音列表已重新加载！\n"
        f"本地 voices/: {old_count} → {new_count} 个（含网页额外文件）\n"
        f"输入关键词测试，或 /voice_list 查看"
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
