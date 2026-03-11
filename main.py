from astrbot.api.star import Star, Context, register, StarTools
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from astrbot.api.message_components import Record
from pathlib import Path
from typing import Dict, List, Set, Optional
import re

ALLOWED_EXT = {'.mp3', '.wav', '.ogg', '.silk', '.amr'}
PAGE_SIZE = 25


@register("airi_voice", "lidure", "输入关键词发送对应语音", "2.3", "https://github.com/Lidure/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        
        # 路径初始化 - 使用框架规范 API
        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用 StarTools 获取规范的数据目录
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_airi_voice")
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
        
        # 解析白名单（支持多行文本）
        whitelist_raw = self.config.get("admin_whitelist", "")
        if isinstance(whitelist_raw, str):
            self.admin_whitelist: Set[str] = set(
                line.strip() for line in whitelist_raw.splitlines() if line.strip()
            )
        elif isinstance(whitelist_raw, list):
            self.admin_whitelist: Set[str] = set(str(x).strip() for x in whitelist_raw if str(x).strip())
        else:
            self.admin_whitelist: Set[str] = set()
        
        # 语音映射
        self.voice_map: Dict[str, str] = {}
        self.sorted_keys: List[str] = []
        
        # 加载语音
        self._load_local_voices()
        self._load_web_voices(self.config)
        self._update_sorted_keys()  # ✅ 修复：初始化后更新排序列表
        
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        
        logger.info(f"[AiriVoice] 初始化完成，共 {len(self.voice_map)} 个语音，权限模式：{self.admin_mode}")

    def _get_user_id(self, event: AstrMessageEvent) -> Optional[str]:
        """从事件中安全提取用户 ID"""
        try:
            # ✅ 修复：使用框架规范方法
            return event.get_sender_id()
        except (AttributeError, TypeError):
            pass
        
        # fallback：兼容旧版本
        try:
            return event.message_obj.sender.user_id
        except AttributeError:
            pass
        
        user_id = getattr(event, 'sender_id', None) or getattr(event, 'user_id', None)
        return str(user_id) if user_id else None

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
                # 相对于插件数据目录解析路径
                abs_path = (self.data_dir / rel_path).resolve()
                
                # 安全校验：防止路径穿越
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
            self._update_sorted_keys()  # ✅ 修复：热更新后同步排序列表
            self.last_pool_len = current_pool_len

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

        msg = f"📦 可用语音（第 {page}/{total_pages} 页，共 {total} 个）：\n\n"
        msg += "\n".join(f"・ {k}" for k in page_keys)

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
        self._update_sorted_keys()  # ✅ 修复：重新加载后更新排序列表
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        
        yield event.plain_result(f"✅ 已重新加载，共 {len(self.voice_map)} 个语音")

    @filter.command("voice.help")
    async def help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        is_admin = self._check_admin(event)
        
        # 构建命令列表（避免空行问题）
        commands = [
            "• /voice.list [页码] - 查看可用语音",
            "• /voice.help - 显示此帮助",
        ]
        if is_admin:
            commands.append("• /voice.reload - 重新加载语音列表 (管理员)")
        
        help_msg = f"""📦 AiriVoice 语音插件

【使用方法】
1. 将语音文件放入 voices/ 目录
2. 或在 AstrBot 网页后台 → 插件配置 → 上传语音
3. 文件名即为关键词（不含扩展名）
4. 直接输入关键词即可发送语音

【触发模式】
• direct: 直接输入关键词触发
• prefix: 使用 #voice 关键词 触发

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
