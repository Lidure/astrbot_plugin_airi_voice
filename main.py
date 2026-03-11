from astrbot.api.star import Star, Context, register
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from astrbot.api.message_components import Record
from pathlib import Path
from typing import Dict, List, Set
import re

ALLOWED_EXT = {'.mp3', '.wav', '.ogg', '.silk', '.amr'}
PAGE_SIZE = 25


@register("airi_voice", "lidure", "输入关键词发送对应语音", "2.1", "https://github.com/Lidure/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        
        # 路径初始化
        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        
        # 配置
        self.config = config or {}
        self.trigger_mode = self.config.get("trigger_mode", "direct")
        if self.trigger_mode not in {"prefix", "direct"}:
            self.trigger_mode = "direct"
        
        # 权限控制
        self.admin_mode = self.config.get("admin_mode", "whitelist")  # whitelist / admin / all
        self.admin_whitelist: Set[str] = set(self.config.get("admin_whitelist", []))
        
        # 语音映射
        self.voice_map: Dict[str, str] = {}
        self.sorted_keys: List[str] = []
        
        # 网页配置监控
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        
        self._load_voices()
        logger.info(f"[AiriVoice] 初始化完成，共 {len(self.voice_map)} 个语音，权限模式：{self.admin_mode}")

    def _load_voices(self):
        """加载所有语音文件"""
        self.voice_map.clear()
        
        # 加载本地 voices 目录
        for file_path in self.voice_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in ALLOWED_EXT:
                keyword = file_path.stem.strip()
                if keyword:
                    self.voice_map[keyword] = str(file_path)
        
        # 加载网页配置的额外语音
        self._load_extra_voices()
        
        self.sorted_keys = sorted(self.voice_map.keys())

    def _load_extra_voices(self):
        """加载网页配置的额外语音"""
        extra_pool = self.config.get("extra_voice_pool", [])
        data_dir = self.voice_dir.parent / "extra_voices"
        data_dir.mkdir(parents=True, exist_ok=True)
        
        for rel_path in extra_pool:
            if not isinstance(rel_path, str) or not rel_path.strip():
                continue
            
            abs_path = data_dir / rel_path
            if abs_path.exists() and abs_path.is_file() and abs_path.suffix.lower() in ALLOWED_EXT:
                keyword = abs_path.stem.strip()
                if keyword:
                    self.voice_map[keyword] = str(abs_path)

    def _check_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否有管理员权限"""
        # 模式：all = 所有人，admin = 平台管理员，whitelist = 白名单
        if self.admin_mode == "all":
            return True
        
        if self.admin_mode == "admin":
            # 尝试获取用户角色信息
            user_info = getattr(event, 'user_info', None)
            if user_info:
                role = getattr(user_info, 'role', None) or (user_info.get('role') if isinstance(user_info, dict) else None)
                if role in ('admin', 'owner', 'master'):
                    return True
            # 备选：检查 event 中的权限标记
            if getattr(event, 'is_admin', False) or getattr(event, 'is_master', False):
                return True
            return False
        
        if self.admin_mode == "whitelist":
            user_id = getattr(event, 'sender_id', None) or getattr(event, 'user_id', None)
            if not user_id:
                # 尝试从 message_obj 获取
                try:
                    user_id = event.message_obj.sender.user_id
                except Exception:
                    pass
            
            if user_id and str(user_id) in self.admin_whitelist:
                return True
            
            # 也检查 uname
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

        # 检查配置变化，自动刷新
        current_pool_len = len(self.config.get("extra_voice_pool", []))
        if current_pool_len > self.last_pool_len:
            self._load_voices()
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
            except Exception as e:
                logger.error(f"[AiriVoice] 发送失败 '{keyword}': {e}")
                yield event.plain_result(f"语音发送失败：{e}")

    @filter.command("voice.list")
    async def list_voices(self, event: AstrMessageEvent):
        """列出所有语音关键词"""
        if not self.sorted_keys:
            yield event.plain_result("当前没有可用语音～\n将语音文件放入 plugins/airi_voice/voices/ 目录即可")
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
        
        self._load_voices()
        self.last_pool_len = len(self.config.get("extra_voice_pool", []))
        yield event.plain_result(f"✅ 已重新加载，共 {len(self.voice_map)} 个语音")

    @filter.command("voice.help")
    async def help(self, event: AstrMessageEvent):
        """显示帮助信息"""
        is_admin = self._check_admin(event)
        
        help_msg = f"""📦 AiriVoice 语音插件

【使用方法】
1. 将语音文件放入 plugins/airi_voice/voices/ 目录
2. 文件名即为关键词（不含扩展名）
3. 直接输入关键词即可发送语音

【触发模式】
• direct: 直接输入关键词触发
• prefix: 使用 #voice 关键词 触发

【命令】
• /voice.list [页码] - 查看可用语音
{f"• /voice.reload - 重新加载语音列表 (管理员)" if is_admin else ""}
• /voice.help - 显示此帮助

【网页配置】
在配置中添加 extra_voice_pool，填入相对于 data/plugin_data/astrbot_plugin_airi_voice/extra_voices/ 的路径"""
        yield event.plain_result(help_msg)

    @filter.command("voice.check")
    async def check_permission(self, event: AstrMessageEvent):
        """检查当前用户权限（调试用）"""
        is_admin = self._check_admin(event)
        user_id = getattr(event, 'sender_id', None) or getattr(event, 'user_id', None)
        
        if not user_id:
            try:
                user_id = event.message_obj.sender.user_id
            except Exception:
                user_id = "未知"
        
        msg = f"🔐 权限检查\n\n"
        msg += f"用户 ID: {user_id}\n"
        msg += f"权限模式：{self.admin_mode}\n"
        msg += f"是否有权限：{'✅ 是' if is_admin else '❌ 否'}\n"
        
        if self.admin_mode == "whitelist" and not is_admin:
            msg += f"\n💡 提示：将您的用户 ID 添加到 admin_whitelist 即可获取权限"
        
        yield event.plain_result(msg)
