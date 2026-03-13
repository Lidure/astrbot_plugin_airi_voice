from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Set
import re
import random

import aiohttp
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Record, Reply
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext


ALLOWED_EXT = {".mp3", ".wav", ".ogg", ".silk", ".amr"}
PAGE_SIZE = 15


@dataclass
class AiriListAllVoicesTool(FunctionTool[AstrAgentContext]):
    """列出当前插件中所有可用的语音名称。"""

    name: str = "airi_list_all_voices"
    description: str = "列出本插件加载的全部语音名称，供 LLM 选择使用。"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "required": [],
        }
    )
    plugin: "AiriVoice" | None = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        if not self.plugin or not self.plugin.voice_map:
            return "当前没有可用语音。"

        names = sorted(self.plugin.voice_map.keys())
        return "当前可用语音名称列表：\n" + "\n".join(names)


@dataclass
class AiriSearchVoicesTool(FunctionTool[AstrAgentContext]):
    """根据关键词筛选语音名称。"""

    name: str = "airi_search_voices"
    description: str = (
        "根据用户给出的关键词，在本插件的语音库中筛选匹配的语音名称。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "用户给出的语音关键词，用于模糊匹配语音名称。",
                }
            },
            "required": ["keyword"],
        }
    )
    plugin: "AiriVoice" | None = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        if not self.plugin or not self.plugin.voice_map:
            return "当前没有可用语音。"

        keyword = (kwargs.get("keyword") or "").strip()
        if not keyword:
            return "请提供要搜索的语音关键词。"

        keyword_lower = keyword.lower()
        matched = [
            name
            for name in self.plugin.voice_map.keys()
            if keyword_lower in name.lower()
        ]

        if not matched:
            return f"未找到包含「{keyword}」的语音名称。"

        matched.sort()
        return (
            f"根据关键词「{keyword}」筛选到的语音名称：\n" + "\n".join(matched)
        )


@dataclass
class AiriSendVoiceTool(FunctionTool[AstrAgentContext]):
    """向当前会话发送指定名称的语音。"""

    name: str = "airi_send_voice"
    description: str = (
        "根据指定的语音名称，向当前会话直接发送对应的语音消息。"
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要发送的语音名称，必须是已存在的语音列表中的一个。",
                }
            },
            "required": ["name"],
        }
    )
    plugin: "AiriVoice" | None = None

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        if not self.plugin or not self.plugin.voice_map:
            return "当前没有可用语音。"

        name = (kwargs.get("name") or "").strip()
        if not name:
            return "请提供要发送的语音名称。"

        path = self.plugin.voice_map.get(name)
        if not path:
            return f"语音「{name}」不存在，请先使用列出/搜索工具确认可用名称。"

        # 从运行上下文中拿到原始事件，直接向当前会话发送语音
        try:
            event = context.context.event
        except Exception:
            event = None

        if event is None:
            return (
                f"无法获取当前会话上下文，未能发送语音「{name}」。"
            )

        try:
            await event.chain_result([Record.fromFileSystem(path)])
            logger.debug(f"[AiriVoice] LLM 工具发送语音：'{name}' → {path}")
            return f"已向当前会话发送语音「{name}」。"
        except FileNotFoundError as e:
            logger.error(f"[AiriVoice] 文件不存在（LLM 工具） '{name}': {e}")
            return f"语音文件不存在：{name}"
        except Exception as e:
            logger.error(f"[AiriVoice] LLM 工具发送失败 '{name}': {e}")
            return f"语音发送失败：{type(e).__name__}"


@register(
    "airi_voice",
    "lidure",
    "输入关键词发送对应语音",
    "2.2",
    "https://github.com/Lidure/astrbot_plugin_airi_voice",
)
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        
        # 路径初始化
        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 StarTools 获取数据目录（持久化）
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_airi_voice")
        
        # 用户添加的语音保存目录（重启不丢）
        self.user_added_dir = self.data_dir / "user_added"
        self.user_added_dir.mkdir(parents=True, exist_ok=True)
        
        # 网页上传目录
        self.extra_voice_dir = self.data_dir / "extra_voices"
        self.extra_voice_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[AiriVoice] 数据目录：{self.data_dir}")
        
        # 配置
        self.config = config or {}
        self.trigger_mode = self.config.get("trigger_mode", "direct")
        if self.trigger_mode not in {"prefix", "direct"}:
            logger.warning(f"[AiriVoice] 无效 trigger_mode，强制使用 direct")
            self.trigger_mode = "direct"
        
        # 权限控制
        self.admin_mode = self.config.get("admin_mode", "whitelist")
        if self.admin_mode not in {"all", "admin", "whitelist"}:
            self.admin_mode = "whitelist"
        
        whitelist_raw = self.config.get("admin_whitelist", "")
        if isinstance(whitelist_raw, str):
            self.admin_whitelist: Set[str] = set(
                line.strip() for line in whitelist_raw.splitlines() if line.strip()
            )
        elif isinstance(whitelist_raw, list):
            self.admin_whitelist: Set[str] = set(str(x).strip() for x in whitelist_raw if str(x).strip())
        else:
            self.admin_whitelist: Set[str] = set()

        # LLM 语音选择模式
        self.llm_select_mode = self.config.get("llm_select_mode", "list")
        if self.llm_select_mode not in {"list", "keyword"}:
            logger.warning(
                f"[AiriVoice] 无效 llm_select_mode，强制使用 list"
            )
            self.llm_select_mode = "list"
        
        # 语音映射
        self.voice_map: Dict[str, str] = {}
        self.sorted_keys: List[str] = []
        
        # 加载所有语音
        self._load_local_voices()          # 本地预置
        self._load_user_added_voices()     # 用户添加（持久化）
        self._load_web_voices(self.config) # 网页上传
        self._update_sorted_keys()
        
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        
        # 注册供 LLM 使用的语音相关工具
        llm_tools = []
        if self.llm_select_mode == "list":
            llm_tools.append(AiriListAllVoicesTool(plugin=self))
        else:
            llm_tools.append(AiriSearchVoicesTool(plugin=self))
        llm_tools.append(AiriSendVoiceTool(plugin=self))

        try:
            # AstrBot >= v4.5.1
            self.context.add_llm_tools(*llm_tools)
            logger.info(
                f"[AiriVoice] 已为 LLM 注册 {len(llm_tools)} 个语音工具，模式：{self.llm_select_mode}"
            )
        except Exception as e:
            logger.error(f"[AiriVoice] 注册 LLM 工具失败：{e}")
        
        logger.info(f"[AiriVoice] 初始化完成，共 {len(self.voice_map)} 个语音，权限模式：{self.admin_mode}")

    def _get_user_id(self, event: AstrMessageEvent) -> Optional[str]:
        """从事件中安全提取用户 ID"""
        try:
            return event.get_sender_id()
        except (AttributeError, TypeError):
            pass
        
        try:
            return event.message_obj.sender.user_id
        except AttributeError:
            pass
        
        user_id = getattr(event, 'sender_id', None) or getattr(event, 'user_id', None)
        return str(user_id) if user_id else None

    def _get_reply_id(self, event: AstrMessageEvent) -> Optional[int]:
        """获取被引用消息的 ID"""
        for seg in event.get_messages():
            if isinstance(seg, Reply):
                try:
                    return int(seg.id)
                except (ValueError, TypeError):
                    pass
        return None

    async def _get_audio_url(self, event: AstrMessageEvent) -> Optional[str]:
        """从引用消息中获取音频 URL"""
        chain = event.get_messages()
        url = None

        def extract_media_url(seg):
            url_ = (
                getattr(seg, "url", None)
                or getattr(seg, "file", None)
                or getattr(seg, "path", None)
            )
            return url_ if url_ and str(url_).startswith("http") else None

        # 遍历引用消息的 chain
        reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
        if reply_seg and hasattr(reply_seg, 'chain') and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Record):
                    url = extract_media_url(seg)
                    if url:
                        break

        # 从原始引用消息中获取（通过 bot API）
        if url is None and hasattr(event, 'bot'):
            if msg_id := self._get_reply_id(event):
                try:
                    raw = await event.bot.get_msg(message_id=msg_id)
                    messages = raw.get("message", [])
                    for seg in messages:
                        if isinstance(seg, dict) and seg.get("type") == "record":
                            if seg_url := seg.get("data", {}).get("url"):
                                url = seg_url
                                break
                except Exception as e:
                    logger.error(f"[AiriVoice] 获取引用消息失败：{e}")

        return url

    async def _download_audio(self, url: str) -> Optional[bytes]:
        """下载音频文件"""
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                return await response.read()
        except Exception as e:
            logger.error(f"[AiriVoice] 下载音频失败：{e}")
            return None

    def _get_file_ext_from_url(self, url: str) -> str:
        """根据 URL 推断文件扩展名"""
        url_lower = url.lower()
        if ".wav" in url_lower:
            return ".wav"
        elif ".ogg" in url_lower:
            return ".ogg"
        elif ".silk" in url_lower:
            return ".silk"
        elif ".amr" in url_lower:
            return ".amr"
        return ".mp3"  # 默认

    def _update_sorted_keys(self):
        """更新排序后的语音关键词列表"""
        self.sorted_keys = sorted(self.voice_map.keys())

    def _load_local_voices(self):
        """加载本地 voices 目录的语音"""
        count = 0
        for file_path in self.voice_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ALLOWED_EXT:
                keyword = file_path.stem.strip()
                if keyword:
                    self.voice_map[keyword] = str(file_path)
                    count += 1
        
        if count > 0:
            logger.info(f"[AiriVoice] 从本地加载 {count} 个语音")

        
    def _load_user_added_voices(self):
        """加载用户通过 voice.add 添加的语音（持久化，重启不丢）"""
        count = 0
        for file_path in self.user_added_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ALLOWED_EXT:
                keyword = file_path.stem.strip()
                if keyword:
                    if keyword in self.voice_map:
                        logger.warning(f"[AiriVoice] 用户添加关键词冲突：'{keyword}' 已存在，将覆盖")
                    self.voice_map[keyword] = str(file_path)
                    count += 1
        
        if count > 0:
            logger.info(f"[AiriVoice] 从用户添加目录加载 {count} 个语音")
            
    def _load_web_voices(self, config: dict = None):
        """加载网页配置的额外语音"""
        if config is None:
            return
        
        extra_pool = config.get("extra_voice_pool", [])
        if not extra_pool:
            return
        
        logger.debug(f"[AiriVoice] 网页相对路径池：{extra_pool}")
        
        loaded = 0
        data_dir_resolved = self.data_dir.resolve()
        
        for rel_path in extra_pool:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            
            try:
                abs_path = (self.data_dir / rel_path).resolve()
                
                if not abs_path.is_relative_to(data_dir_resolved):
                    logger.warning(f"[AiriVoice] 检测到非法路径：{rel_path}")
                    continue
            except (ValueError, OSError) as e:
                logger.warning(f"[AiriVoice] 路径解析失败：{rel_path} - {e}")
                continue
            
            if abs_path.exists() and abs_path.is_file():
                if abs_path.suffix.lower() not in ALLOWED_EXT:
                    logger.warning(f"[AiriVoice] 忽略非音频文件：{abs_path}")
                    continue
                
                keyword = abs_path.stem.strip()
                if keyword:
                    self.voice_map[keyword] = str(abs_path)
                    loaded += 1
                    logger.debug(f"[AiriVoice] 网页加载：'{keyword}' → {abs_path}")
            else:
                logger.warning(f"[AiriVoice] 文件不存在：{abs_path} (相对：{rel_path})")
        
        if loaded > 0:
            logger.info(f"[AiriVoice] 从网页配置加载 {loaded} 个额外语音")

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否有管理员权限"""
        if self.admin_mode == "all":
            return True
        
        if self.admin_mode == "admin":
            if getattr(event, 'is_admin', False) or getattr(event, 'is_master', False):
                return True
            try:
                role = event.get_platform_user_role()
                if role in ('admin', 'owner', 'master'):
                    return True
            except AttributeError:
                pass
            return False
        
        if self.admin_mode == "whitelist":
            user_id = self._get_user_id(event)
            if user_id and user_id in self.admin_whitelist:
                return True
            
            uname = getattr(event, 'sender_name', None) or getattr(event, 'nickname', None)
            if uname and uname in self.admin_whitelist:
                return True
            
            return False
        
        return False

    @filter.regex(r"^\s*.+\s*$")
    async def voice_handler(self, event: AstrMessageEvent):
        """语音触发处理器"""
        text = (event.message_str or "").strip()
        if not text:
            return

        # 自动检测配置变化（网页上传后自动刷新）
        current_pool_len = len(self.config.get("extra_voice_pool", []))
        if current_pool_len > self.last_pool_len:
            logger.info("[AiriVoice] 检测到网页配置变化，自动刷新语音列表")
            self._load_web_voices(self.config)
            self._update_sorted_keys()
            self.last_pool_len = current_pool_len

        # 随机语音：支持「随机发条语音 / 随机语音」全局随机，
        # 以及「随机XX」根据关键词随机选择匹配的语音
        if text.startswith("随机") and self.voice_map:
            # 全局随机
            if text in {"随机发条语音", "随机语音"}:
                name = random.choice(list(self.voice_map.keys()))
                matched_path = self.voice_map.get(name)
                if matched_path:
                    try:
                        yield event.chain_result([Record.fromFileSystem(matched_path)])
                        logger.debug(f"[AiriVoice] 随机发送语音（全局）：'{name}'")
                    except FileNotFoundError as e:
                        logger.error(f"[AiriVoice] 随机文件不存在 '{name}': {e}")
                        yield event.plain_result("语音文件不存在")
                    except Exception as e:
                        logger.error(f"[AiriVoice] 随机发送失败 '{name}': {e}")
                        yield event.plain_result(f"语音发送失败：{type(e).__name__}")
                else:
                    yield event.plain_result("当前没有可用语音～")
                return

            # 按关键词随机：随机XX 或 随机 XX
            m = re.match(r"^随机\s*(.+)$", text)
            if m:
                kw = m.group(1).strip()
                if not kw:
                    return
                candidates = [
                    name for name in self.voice_map.keys() if kw in name
                ]
                if not candidates:
                    yield event.plain_result(f"未找到包含「{kw}」的语音")
                    return

                name = random.choice(candidates)
                matched_path = self.voice_map.get(name)
                if matched_path:
                    try:
                        yield event.chain_result([Record.fromFileSystem(matched_path)])
                        logger.debug(
                            f"[AiriVoice] 随机发送语音（关键词「{kw}」）：'{name}'"
                        )
                    except FileNotFoundError as e:
                        logger.error(f"[AiriVoice] 随机文件不存在 '{name}': {e}")
                        yield event.plain_result("语音文件不存在")
                    except Exception as e:
                        logger.error(f"[AiriVoice] 随机发送失败 '{name}': {e}")
                        yield event.plain_result(f"语音发送失败：{type(e).__name__}")
                else:
                    yield event.plain_result("当前没有可用语音～")
                return

        # 获取关键词
        keyword = text
        if self.trigger_mode == "prefix":
            match = re.search(r"^#voice\s+(.+)", text, re.I)
            if not match:
                return
            keyword = match.group(1).strip()

        # 发送语音
        matched_path = self.voice_map.get(keyword)
        if matched_path:
            try:
                yield event.chain_result([Record.fromFileSystem(matched_path)])
                logger.debug(f"[AiriVoice] 发送语音：'{keyword}'")
            except FileNotFoundError as e:
                logger.error(f"[AiriVoice] 文件不存在 '{keyword}': {e}")
                yield event.plain_result(f"语音文件不存在")
            except Exception as e:
                logger.error(f"[AiriVoice] 发送失败 '{keyword}': {e}")
                yield event.plain_result(f"语音发送失败：{type(e).__name__}")

    @filter.command("voice.add")
    async def voice_add(self, event: AstrMessageEvent, name: str):
        """
        通过引用语音消息添加新语音
        用法：引用一条语音消息，然后发送 /voice.add 名字
        """
        # 权限检查
        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员使用")
            return

        # 检查是否有引用消息
        if not self._get_reply_id(event):
            yield event.plain_result("❌ 请引用一条语音消息后再使用此命令")
            return

        # 检查名字是否合法
        if not name or name.strip() == "":
            yield event.plain_result("❌ 请提供语音名称，例如：/voice.add 打卡啦摩托")
            return

        name = name.strip()

        # 检查是否已存在
        if name in self.voice_map:
            yield event.plain_result(f"⚠️ 语音「{name}」已存在，如需覆盖请先删除旧语音")
            return

        # 获取音频 URL
        audio_url = await self._get_audio_url(event)
        if not audio_url:
            yield event.plain_result("❌ 未能从引用的消息中提取到音频，请确保引用的是语音消息")
            return

        logger.debug(f"[AiriVoice] 获取到音频 URL: {audio_url}")

        # 下载音频
        audio_data = await self._download_audio(audio_url)
        if not audio_data:
            yield event.plain_result("❌ 音频下载失败，请稍后重试")
            return

        # 保存到持久化目录（user_added）
        ext = self._get_file_ext_from_url(audio_url)
        file_path = self.user_added_dir / f"{name}{ext}"

        try:
            with open(file_path, "wb") as f:
                f.write(audio_data)
            
            self.voice_map[name] = str(file_path)
            self._update_sorted_keys()
            
            yield event.plain_result(f"✅ 语音「{name}」添加成功！\n📁 文件：{name}{ext}\n💾 大小：{len(audio_data) / 1024:.2f} KB")
        except Exception as e:
            logger.error(f"[AiriVoice] 保存语音失败：{e}")
            yield event.plain_result(f"❌ 保存语音失败：{str(e)}")

    @filter.command("voice.delete")
    async def voice_delete(self, event: AstrMessageEvent, name: str):
        """删除语音"""
        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员使用")
            return

        if name not in self.voice_map:
            yield event.plain_result(f"❌ 语音「{name}」不存在")
            return

        file_path = Path(self.voice_map[name])
        
        # 只允许删除 user_added 目录下的文件
        if not str(file_path.resolve()).startswith(str(self.user_added_dir.resolve())):
            yield event.plain_result(f"⚠️ 只能删除通过 /voice.add 添加的语音，本地 voices/ 和网页上传的文件请手动管理")
            return

        try:
            file_path.unlink()
            del self.voice_map[name]
            self._update_sorted_keys()
            
            yield event.plain_result(f"✅ 语音「{name}」已删除")
        except Exception as e:
            logger.error(f"[AiriVoice] 删除语音失败：{e}")
            yield event.plain_result(f"❌ 删除失败：{str(e)}")

    @filter.command("voice.list")
    async def list_voices(self, event: AstrMessageEvent):
        """列出所有语音关键词"""
        if not self.sorted_keys:
            yield event.plain_result("当前没有可用语音～\n将语音文件放入 voices/ 目录或通过网页上传")
            return

        args = (event.message_str or "").strip().split()
        page = max(1, int(args[1])) if len(args) > 1 and args[1].isdigit() else 1
        
        total = len(self.sorted_keys)
        total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
        
        if page > total_pages:
            yield event.plain_result(f"页码过大～总共 {total_pages} 页")
            return

        start = (page - 1) * PAGE_SIZE
        page_keys = self.sorted_keys[start:start + PAGE_SIZE]

        msg = f"📋 可用语音（第 {page}/{total_pages} 页，共 {total} 个）：\n\n"
        msg += "\n".join(f"• {k}" for k in page_keys)

        if total_pages > 1:
            nav = []
            if page > 1:
                nav.append(f"/voice.list {page-1} ← 上一页")
            if page < total_pages:
                nav.append(f"/voice.list {page+1} → 下一页")
            msg += "\n\n" + "  |  ".join(nav)

        yield event.plain_result(msg)

    @filter.command("voice.reload")
    async def reload_voices(self, event: AstrMessageEvent):
        """重新加载语音列表（需要管理员权限）"""
        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员使用")
            return
        
        self._load_local_voices()
        self._load_web_voices(self.config)
        self._update_sorted_keys()
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        
        yield event.plain_result(f"✅ 已重新加载，共 {len(self.voice_map)} 个语音")

    @filter.command("voice.help")
    async def help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        is_admin = self._check_admin(event)
        
        commands = [
            "📋 /voice.list [页码] - 查看可用语音",
            "❓ /voice.help - 显示此帮助",
        ]
        if is_admin:
            commands.append("➕ /voice.add 名字 - 引用语音消息添加新语音 (管理员)")
            commands.append("🗑️ /voice.delete 名字 - 删除语音 (管理员)")
            commands.append("🔄 /voice.reload - 重新加载语音列表 (管理员)")
        
        help_msg = f"""🌸 AiriVoice 语音插件

【使用方法】
1. 将语音文件放入 voices/ 目录
2. 或在 AstrBot 网页后台 → 插件配置 → 上传语音
3. 或引用语音消息发送 /voice.add 名字
4. 文件名即为关键词（不含扩展名）
5. 直接输入关键词即可发送语音

【触发模式】
🔹 direct: 直接输入关键词触发
🔹 prefix: 使用 #voice 关键词 触发

【命令】
{chr(10).join(commands)}"""
        
        yield event.plain_result(help_msg)

    @filter.command("voice.check")
    async def check_permission(self, event: AstrMessageEvent):
        """检查当前用户权限（调试用）"""
        is_admin = self._check_admin(event)
        user_id = self._get_user_id(event) or "未知"
        
        msg = f"🔐 权限检查\n\n"
        msg += f"用户 ID: {user_id}\n"
        msg += f"权限模式：{self.admin_mode}\n"
        msg += f"是否有权限：{'✅ 是' if is_admin else '❌ 否'}\n"
        
        if self.admin_mode == "whitelist" and not is_admin:
            msg += f"\n💡 提示：在 AstrBot 网页后台 → 插件配置 → admin_whitelist 中添加您的用户 ID"
        
        yield event.plain_result(msg)
