import os
import json
import aiohttp
from pathlib import Path
from typing import Optional, List, Any

# 修正导入路径，适配新版 AstrBot
from astrbot.api import Star, Context
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.config.default import VERSION

# 尝试导入 event 装饰器，如果失败则使用手动注册
try:
    from astrbot.api.event import filter
    event_filter = filter
except ImportError:
    event_filter = None

@Star.register(
    name="astrbot_plugin_airi_voice",
    version="2.4.1", # 版本号微调以示修复
    author="lidure",
    description="输入关键词即可触发可爱语音，支持引用添加、网页上传和权限控制。"
)
class AiriVoicePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.config = context.get_config()
        
        # 获取数据目录 (用于持久化存储用户上传的语音)
        # 在较新版本中，get_data_dir 可能直接返回 Path 对象
        try:
            self.data_dir = context.get_data_dir()
        except AttributeError:
            # 兼容旧写法
            self.data_dir = Path(context.app_config['data_path']) / "plugin_data" / "astrbot_plugin_airi_voice"
            
        self.extra_voice_dir = self.data_dir / "extra_voices"
        
        # 确保目录存在
        if not self.extra_voice_dir.exists():
            self.extra_voice_dir.mkdir(parents=True, exist_ok=True)
            
        # 初始化配置项
        self._init_config()
        
        # 构建完整语音列表
        self.voice_map = self._build_voice_map()
        
        # 注册消息处理器 (替代 @on_message 装饰器)
        # 这种方式在所有版本中都有效
        self.context.register_event_listener(self.on_message_handler)

    def _init_config(self):
        """初始化配置字典并确保保存"""
        defaults = {
            "extra_voice_pool": [],
            "trigger_mode": "direct", # direct or prefix
            "admin_mode": "whitelist", # all, admin, whitelist
            "admin_whitelist": []
        }
        
        updated = False
        for key, value in defaults.items():
            if key not in self.config:
                self.config[key] = value
                updated = True
        
        if updated:
            self.save_config()

    def _build_voice_map(self) -> dict:
        """扫描所有可用语音文件，构建 {关键词: 文件路径} 映射"""
        voice_map = {}
        
        # 1. 扫描本地 voices 目录 (插件自带)
        local_voice_dir = Path(__file__).parent / "voices"
        if local_voice_dir.exists():
            for f in local_voice_dir.iterdir():
                if f.is_file() and f.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                    key = f.stem
                    voice_map[key] = str(f)

        # 2. 扫描额外 voices 目录 (用户添加/网页上传)
        if self.extra_voice_dir.exists():
            pool = self.config.get("extra_voice_pool", [])
            for f in self.extra_voice_dir.iterdir():
                if f.is_file() and f.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                    key = f.stem
                    # 策略：如果配置池为空，则加载所有；否则只加载池中的
                    if not pool or key in pool:
                        voice_map[key] = str(f)
                        
        return voice_map

    def save_config(self):
        """保存配置到 config.json"""
        try:
            # 获取配置文件路径
            config_path = Path(__file__).parent / "config.json"
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            self.logger.info("配置文件已保存")
        except Exception as e:
            self.logger.error(f"保存配置失败: {e}")

    def _check_permission(self, event: AstrMessageEvent) -> bool:
        """检查用户权限"""
        mode = self.config.get("admin_mode", "whitelist")
        
        # 获取管理员ID列表 (适配不同版本)
        try:
            admin_ids = self.context.get_admin_ids()
        except AttributeError:
            admin_ids = self.context.app_config.get('admin_id', [])
            if isinstance(admin_ids, str):
                admin_ids = [admin_ids]

        if mode == "all":
            return True
        if mode == "admin":
            sender_id = event.get_sender_id()
            return sender_id in admin_ids
        
        # whitelist 模式
        uid = event.get_sender_id()
        nickname = event.get_sender_name()
        allow_list = self.config.get("admin_whitelist", [])
        return uid in allow_list or nickname in allow_list or uid in admin_ids

    async def _download_file(self, url: str, save_path: Path) -> bool:
        """下载文件辅助函数"""
        try:
            # 适配新版 aiohttp 用法
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        with open(save_path, 'wb') as f:
                            f.write(await resp.read())
                        return True
        except Exception as e:
            self.logger.error(f"下载文件失败: {e}")
        return False

    async def on_message_handler(self, event: AstrMessageEvent):
        """统一消息处理器"""
        message_chain = event.get_message_chain()
        text = message_chain.text().strip()
        
        if not text:
            return

        # 1. 处理命令 (以 / 开头)
        if text.startswith("/"):
            parts = text.split()
            cmd = parts[0]
            args = parts[1:] if len(parts) > 1 else []

            # --- 命令: voice.add ---
            if cmd == "/voice.add":
                if not self._check_permission(event):
                    await event.send("❌ 权限不足：只有管理员或白名单用户可添加语音。")
                    return
                
                ref_msg = event.get_message_ref()
                if not ref_msg:
                    await event.send("❌ 用法错误：请引用一条语音消息后，再发送 `/voice.add 关键词`")
                    return
                
                if not args:
                    await event.send("❌ 用法错误：请指定关键词，例如 `/voice.add 早上好`")
                    return

                voice_name = args[0]
                
                # 查找引用消息中的语音/文件部分
                file_url = None
                file_ext = "mp3"
                
                ref_chain = ref_msg.get_message_chain()
                for comp in ref_chain:
                    # 检查组件类型，适配不同平台
                    comp_type = getattr(comp, 'type', '')
                    if comp_type in ['voice', 'file', 'record'] or (hasattr(comp, 'url') and comp_type):
                        if hasattr(comp, 'url') and comp.url:
                            file_url = comp.url
                            if hasattr(comp, 'name') and comp.name and '.' in comp.name:
                                file_ext = comp.name.split('.')[-1]
                            elif file_url and '.' in file_url:
                                # 清理 URL 参数
                                clean_url = file_url.split('?')[0]
                                file_ext = clean_url.split('.')[-1]
                            break
                
                if not file_url:
                    await event.send("❌ 未找到引用的语音文件，请确保引用的是语音消息。")
                    return

                # 构造安全文件名
                safe_name = "".join([c for c in voice_name if c.isalnum() or c in "_-"])
                if not safe_name:
                    await event.send("❌ 关键词包含非法字符，请使用字母、数字、下划线或中划线。")
                    return

                file_name = f"{safe_name}.{file_ext}"
                save_path = self.extra_voice_dir / file_name

                # 下载文件
                if await self._download_file(file_url, save_path):
                    # ✅ 核心逻辑：更新配置并保存
                    pool = self.config.get("extra_voice_pool", [])
                    if safe_name not in pool:
                        pool.append(safe_name)
                        self.config["extra_voice_pool"] = pool
                        self.save_config() # 持久化保存
                    
                    # 刷新内存中的映射
                    self.voice_map = self._build_voice_map()
                    
                    await event.send(f"✅ 语音 `{safe_name}` 添加成功！\n已自动保存到配置文件，重启后依然有效。")
                else:
                    await event.send("❌ 语音文件下载失败。")
                return

            # --- 命令: voice.delete ---
            if cmd == "/voice.delete":
                if not self._check_permission(event):
                    await event.send("❌ 权限不足。")
                    return
                if not args:
                    await event.send("❌ 用法：`/voice.delete 关键词`")
                    return
                
                name = args[0]
                found_file = None
                for f in self.extra_voice_dir.iterdir():
                    if f.stem == name:
                        found_file = f
                        break
                
                if found_file:
                    try:
                        found_file.unlink()
                        # 从配置池移除
                        pool = self.config.get("extra_voice_pool", [])
                        if name in pool:
                            pool.remove(name)
                            self.config["extra_voice_pool"] = pool
                            self.save_config()
                        self.voice_map = self._build_voice_map()
                        await event.send(f"🗑️ 语音 `{name}` 已删除。")
                    except Exception as e:
                        await event.send(f"❌ 删除失败: {e}")
                else:
                    await event.send(f"❌ 未找到名为 `{name}` 的用户自定义语音。")
                return

            # --- 命令: voice.reload ---
            if cmd == "/voice.reload":
                if not self._check_permission(event):
                    await event.send("❌ 权限不足。")
                    return
                self.voice_map = self._build_voice_map()
                await event.send("🔄 语音列表已重新加载。")
                return

            # --- 命令: voice.list ---
            if cmd == "/voice.list":
                page = 1
                if args and args[0].isdigit():
                    page = int(args[0])
                
                keys = sorted(self.voice_map.keys())
                per_page = 25
                total_pages = (len(keys) + per_page - 1) // per_page if keys else 1
                
                if page < 1: page = 1
                if page > total_pages: page = total_pages
                
                start_idx = (page - 1) * per_page
                end_idx = start_idx + per_page
                current_keys = keys[start_idx:end_idx]
                
                msg = f"📄 语音列表 (第 {page}/{total_pages} 页，共 {len(keys)} 条):\n"
                for k in current_keys:
                    msg += f"• {k}\n"
                
                if total_pages > 1:
                    msg += "\n💡 使用 `/voice.list 页码` 翻页"
                
                await event.send(msg)
                return

            # --- 命令: voice.help ---
            if cmd == "/voice.help":
                help_text = (
                    "🌸 **Airi Voice 帮助**\n\n"
                    "1. **触发**: 直接发送关键词 (如 `早上好`)\n"
                    "2. **添加**: 引用语音消息 + `/voice.add 关键词`\n"
                    "3. **列表**: `/voice.list`\n"
                    f"4. **模式**: 当前为 `{self.config.get('trigger_mode', 'direct')}` 模式\n"
                    "   - `direct`: 直接发关键词\n"
                    "   - `prefix`: 需发送 `#voice 关键词`"
                )
                await event.send(help_text)
                return
            
            # --- 命令: voice.check ---
            if cmd == "/voice.check":
                is_admin = self._check_permission(event)
                status = "✅ 有权限" if is_admin else "❌ 无权限"
                await event.send(f"当前用户权限状态: {status}\n模式: {self.config.get('admin_mode')}")
                return

        # 2. 处理语音触发
        trigger_mode = self.config.get("trigger_mode", "direct")
        keyword = text

        # 前缀模式处理
        if trigger_mode == "prefix":
            if keyword.startswith("#voice "):
                keyword = keyword[7:].strip()
            else:
                return # 非前缀开头，不处理
        
        # 匹配语音
        if keyword in self.voice_map:
            file_path = self.voice_map[keyword]
            if os.path.exists(file_path):
                try:
                    # 发送语音文件
                    # 使用 event.send_file 是最通用的方法
                    await event.send_file(file_path)
                except Exception as e:
                    self.logger.error(f"发送语音失败: {e}")
                    await event.send(f"⚠️ 语音文件存在但发送失败: {e}")
            else:
                self.logger.warning(f"语音文件不存在: {file_path}")
                # 可选：自动从列表中移除失效条目
                if keyword in self.voice_map:
                    del self.voice_map[keyword]
