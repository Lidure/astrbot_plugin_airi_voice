from astrbot.api.star import Star, Context, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from astrbot.api.message_components import Record  # 添加这个导入
from pathlib import Path
from typing import Dict
import re
import os

ALLOWED_EXT = {'.mp3', '.wav', '.ogg', '.silk', '.amr'}

@register("airi_voice", "lidure", "输入关键词发送对应语音（本地 + 网页上传 + 引用保存）", "1.5", "https://github.com/Lidure/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
    
        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"
    
        self.data_dir = self.plugin_dir.parent.parent.parent / "data" / "plugin_data" / "astrbot_plugin_airi_voice"
        self.extra_voice_dir = self.data_dir / "extra_voices"
        self.extra_voice_dir.mkdir(parents=True, exist_ok=True)
    
        logger.info(f"[AiriVoice] 数据目录：{self.data_dir}")
    
        self.voice_map: Dict[str, str] = {}
        self.sorted_keys: list[str] = []
    
        self._load_local_voices()
    
        self.config = config
        self.trigger_mode = (config or {}).get("trigger_mode", "direct")
        if self.trigger_mode not in {"prefix", "direct"}:
            logger.warning(f"[AiriVoice] 无效 trigger_mode '{self.trigger_mode}'，强制使用 direct")
            self.trigger_mode = "direct"
        logger.info(f"[AiriVoice] 当前触发模式：{self.trigger_mode}")
    
        self._load_web_voices(config)
        self.last_pool_len = len(config.get("extra_voice_pool", [])) if config else 0
    
        logger.info(f"[AiriVoice] 初始化完成，当前语音总数：{len(self.voice_map)} 个")

    def _load_local_voices(self):
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[AiriVoice] 已创建本地 voices 目录")

        count = 0
        for file_path in self.voice_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ALLOWED_EXT:
                keyword = file_path.stem.strip()
                if keyword in self.voice_map:
                    logger.warning(f"[AiriVoice] 本地关键词冲突：'{keyword}' 已存在，将被覆盖")
                self.voice_map[keyword] = str(file_path)
                count += 1
                logger.debug(f"[AiriVoice] 本地加载：'{keyword}' → {file_path}")

        if count > 0:
            logger.info(f"[AiriVoice] 从本地 voices 加载 {count} 个语音")

        self.sorted_keys = sorted(self.voice_map.keys())

    def _load_web_voices(self, config: dict = None):
        if config is None:
            logger.info("[AiriVoice] 未收到 config，不加载网页语音")
            return

        extra_pool = config.get("extra_voice_pool", [])
        if not extra_pool:
            logger.info("[AiriVoice] 无 extra_voice_pool 配置")
            return

        logger.info(f"[AiriVoice] 网页相对路径池：{extra_pool}")

        loaded = 0
        data_dir_resolved = self.data_dir.resolve()
        for rel_path in extra_pool:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue

            try:
                abs_path = (self.data_dir / rel_path).resolve()
                if not abs_path.is_relative_to(data_dir_resolved):
                    logger.warning(f"[AiriVoice] 检测到非法路径尝试：{rel_path} → {abs_path}")
                    continue
            except Exception as e:
                logger.warning(f"[AiriVoice] 路径解析失败：{rel_path} - {e}")
                continue

            if abs_path.exists() and abs_path.is_file():
                if abs_path.suffix.lower() not in ALLOWED_EXT:
                    logger.warning(f"[AiriVoice] 忽略非音频文件：{abs_path}")
                    continue
                keyword = abs_path.stem.strip()
                if keyword in self.voice_map:
                    logger.warning(f"[AiriVoice] 网页关键词冲突：'{keyword}' 已存在，将覆盖")
                self.voice_map[keyword] = str(abs_path)
                loaded += 1
                logger.info(f"[AiriVoice] 网页加载成功：'{keyword}' → {abs_path}")
            else:
                logger.warning(f"[AiriVoice] 网页文件不存在：{abs_path} (相对：{rel_path})")

        if loaded > 0:
            logger.info(f"[AiriVoice] 从网页配置加载 {loaded} 个额外语音")

        self.sorted_keys = sorted(self.voice_map.keys())

    @filter.regex(r"^\s*.+\s*$")
    async def voice_handler(self, event: AstrMessageEvent):
        text = (event.message_str or "").strip()
        if not text:
            return

        current_pool_len = len(self.config.get("extra_voice_pool", [])) if self.config else 0
        if current_pool_len > self.last_pool_len:
            logger.info("[AiriVoice] 检测到网页配置变化，自动刷新语音列表")
            self._load_web_voices(self.config)
            self.last_pool_len = current_pool_len

        keyword = text

        if self.trigger_mode == "prefix":
            match = re.search(r"^#voice\s+(.+)", text, re.I)
            if not match:
                return
            keyword = match.group(1).strip()

        matched_path = self.voice_map.get(keyword)
        if matched_path is None:
            return

        try:
            logger.info(f"[AiriVoice] 触发语音（模式：{self.trigger_mode}）：'{keyword}' → {matched_path}")
            chain = [Record.fromFileSystem(matched_path)]
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"[AiriVoice] 发送失败 '{keyword}': {str(e)}", exc_info=True)
            yield event.plain_result(f"语音发送失败：{str(e)}")

    @filter.command("voice.add")
    async def add_voice(self, event: AstrMessageEvent):
        """引用一条语音消息 + voice.add 名字 → 保存为 silk 文件"""
        logger.debug(f"[AiriVoice] raw_message: {getattr(event, 'raw_message', '无 raw_message')}")
        
        # 检查是否有引用消息
        raw_msg = getattr(event, 'raw_message', '') or ''
        
        # 方法1：尝试从 CQ 码获取 reply id
        reply_match = re.search(r'\[CQ:reply,id=(\d+)\]', raw_msg)
        reply_id = None
        
        if reply_match:
            reply_id = int(reply_match.group(1))
        else:
            # 方法2：尝试从 event 对象获取引用信息
            if hasattr(event, 'reply') and event.reply:
                reply_id = event.reply.get('id') if isinstance(event.reply, dict) else getattr(event.reply, 'id', None)
            elif hasattr(event, 'message') and event.message:
                # 检查消息链中是否有 reply segment
                for seg in event.message:
                    if hasattr(seg, 'type') and seg.type == 'reply':
                        reply_id = getattr(seg, 'id', None) or getattr(seg, 'seq', None)
                        break
        
        if not reply_id:
            yield event.plain_result("请先引用（回复）一条语音消息，再使用 voice.add 名字\n（长按语音 → 回复/引用）")
            return
    
        logger.info(f"[AiriVoice] 检测到引用消息 ID: {reply_id}")
    
        try:
            # 拉取被引用消息完整内容
            quoted_msg = await self.context.bot.get_msg(message_id=reply_id)
            logger.debug(f"[AiriVoice] get_msg 成功：{quoted_msg}")
        except Exception as e:
            logger.error(f"[AiriVoice] get_msg 失败：{e}")
            yield event.plain_result(f"无法获取引用的消息内容：{str(e)}，请稍后再试")
            return
    
        # 从 quoted_msg 中提取语音文件
        voice_data = None
        voice_file_path = None
        
        # 获取消息内容
        quoted_raw = getattr(quoted_msg, 'message', '') or ''
        logger.debug(f"[AiriVoice] quoted_msg.message 类型：{type(quoted_raw)}, 内容：{quoted_raw}")
        
        if isinstance(quoted_raw, str):
            # 从 CQ 码字符串找 record
            record_match = re.search(r'\[CQ:record,file=([^,\]]+)', quoted_raw)
            if record_match:
                file_id = record_match.group(1)
                logger.info(f"[AiriVoice] 从 CQ 码找到语音 file_id: {file_id}")
                try:
                    # download_file 可能返回文件路径或二进制数据
                    result = await self.context.bot.download_file(file_id)
                    logger.debug(f"[AiriVoice] download_file 返回类型：{type(result)}")
                    
                    if isinstance(result, str) and os.path.exists(result):
                        # 返回的是文件路径
                        voice_file_path = result
                        logger.info(f"[AiriVoice] 语音文件路径：{voice_file_path}")
                    elif isinstance(result, bytes):
                        # 返回的是二进制数据
                        voice_data = result
                        logger.info(f"[AiriVoice] 语音数据大小：{len(voice_data)} bytes")
                    else:
                        yield event.plain_result("无法解析语音文件数据")
                        return
                except Exception as e:
                    logger.error(f"[AiriVoice] 下载失败：{e}")
                    yield event.plain_result(f"无法下载引用的语音文件：{str(e)}")
                    return
            else:
                yield event.plain_result("引用的消息中没有找到语音（record）")
                return
        elif isinstance(quoted_raw, list):
            # 如果是 segment list
            for seg in quoted_raw:
                seg_type = getattr(seg, 'type', '') or (seg.get('type') if isinstance(seg, dict) else '')
                if seg_type == 'record':
                    # 获取 file_id 或 file 字段
                    file_id = getattr(seg, 'file', None) or (seg.get('file') if isinstance(seg, dict) else None)
                    if file_id:
                        logger.info(f"[AiriVoice] 从 segment 找到语音 file_id: {file_id}")
                        try:
                            result = await self.context.bot.download_file(file_id)
                            logger.debug(f"[AiriVoice] download_file 返回类型：{type(result)}")
                            
                            if isinstance(result, str) and os.path.exists(result):
                                voice_file_path = result
                            elif isinstance(result, bytes):
                                voice_data = result
                            else:
                                yield event.plain_result("无法解析语音文件数据")
                                return
                            break
                        except Exception as e:
                            logger.error(f"[AiriVoice] 下载失败：{e}")
                            yield event.plain_result(f"无法下载引用的语音文件：{str(e)}")
                            return
                    else:
                        yield event.plain_result("引用的语音消息中没有找到 file 字段")
                        return
            else:
                yield event.plain_result("引用的消息中没有找到语音（record）segment")
                return
        else:
            yield event.plain_result(f"无法处理的消息格式：{type(quoted_raw)}")
            return
    
        # 提取名字
        args = (event.message_str or "").strip().split(maxsplit=1)
        if len(args) < 2:
            yield event.plain_result("用法：voice.add 名字\n请引用一条语音消息")
            return
    
        name = args[1].strip()
        if not name:
            yield event.plain_result("名字不能为空")
            return
    
        # 保存
        save_name = f"{name}.silk"
        save_path = self.voice_dir / save_name
    
        try:
            if voice_file_path:
                # 从文件路径复制
                import shutil
                shutil.copy2(voice_file_path, save_path)
                logger.info(f"[AiriVoice] 从文件路径复制：{voice_file_path} → {save_path}")
            elif voice_data:
                # 从二进制数据写入
                with open(save_path, 'wb') as f:
                    f.write(voice_data)
                logger.info(f"[AiriVoice] 从二进制数据保存：{save_name} → {save_path}")
            else:
                yield event.plain_result("没有获取到语音数据")
                return
    
            keyword = name.strip()
            if keyword in self.voice_map:
                logger.warning(f"[AiriVoice] 关键词冲突：'{keyword}' 已存在，将覆盖")
            self.voice_map[keyword] = str(save_path)
            self.sorted_keys = sorted(self.voice_map.keys())
    
            yield event.plain_result(f"已保存语音为 '{keyword}'！\n后续直接输入 {keyword} 即可触发发送～")
        except Exception as e:
            logger.error(f"[AiriVoice] 保存失败：{e}", exc_info=True)
            yield event.plain_result(f"保存失败：{str(e)}")

    @filter.command("voice.list")
    async def list_voices(self, event: AstrMessageEvent):
        if not self.sorted_keys:
            yield event.plain_result("当前没有可用语音～快去 voices/ 或网页配置添加吧！")
            return

        args = (event.message_str or "").strip().split()
        page = 1
        if len(args) > 1 and args[1].isdigit():
            page = int(args[1])
            if page < 1:
                page = 1

        total = len(self.sorted_keys)
        page_size = 25
        total_pages = (total + page_size - 1) // page_size

        if page > total_pages:
            yield event.plain_result(f"页码过大～总共只有 {total_pages} 页（共 {total} 个关键词）")
            return

        start = (page - 1) * page_size
        end = start + page_size
        page_keys = self.sorted_keys[start:end]

        msg = f"可用语音关键词（第 {page}/{total_pages} 页，共 {total} 个）：\n"
        for k in page_keys:
            msg += f"・ {k}\n"

        nav = ""
        if total_pages > 1:
            if page > 1:
                nav += f" /voice.list {page-1} ← 上一页"
            if page < total_pages:
                nav += f" /voice.list {page+1} → 下一页"
            if nav:
                msg += f"\n{nav.strip()}"

        yield event.plain_result(msg)
