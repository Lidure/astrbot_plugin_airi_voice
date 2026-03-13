import os
import json
import aiohttp
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

# AstrBot v4+ 核心导入
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import MessageType

# ================= 插件元数据 =================
__plugin_name__ = "airi_voice"
__version__ = "2.5.1-Fix"
__author__ = "lidure"
__description__ = "爱理语音插件：支持关键词触发、引用添加语音、自动保存配置到本地。"

# ================= 全局状态 =================
# 这些变量将在 init_plugin 中初始化
PLUGIN_PATH: Optional[Path] = None
DATA_DIR: Optional[Path] = None
EXTRA_VOICE_DIR: Optional[Path] = None
CONFIG: Dict[str, Any] = {}
VOICE_MAP: Dict[str, str] = {}  # {keyword: file_path}

# ================= 配置管理 =================

def _get_config_path() -> Path:
    """获取配置文件路径"""
    return PLUGIN_PATH / "config.json"

def load_config():
    """加载配置，如果不存在则创建默认配置"""
    global CONFIG
    config_path = _get_config_path()
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
            logger.info(f"[{__plugin_name__}] 配置加载成功")
        except Exception as e:
            logger.error(f"[{__plugin_name__}] 配置文件损坏，重置为默认: {e}")
            CONFIG = _get_default_config()
            save_config()
    else:
        CONFIG = _get_default_config()
        save_config()
        logger.info(f"[{__plugin_name__}] 创建新配置文件")

def _get_default_config() -> Dict[str, Any]:
    """返回默认配置字典"""
    return {
        "extra_voice_pool": [],       # 用户添加的语音关键词列表
        "trigger_mode": "direct",     # direct: 直接发送关键词; prefix: 需要 #voice 前缀
        "admin_mode": "whitelist",    # all: 所有人; admin: 仅管理员; whitelist: 白名单
        "admin_whitelist": []         # 白名单用户ID或昵称
    }

def save_config():
    """将当前配置保存到磁盘"""
    config_path = _get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=4)
        logger.debug(f"[{__plugin_name__}] 配置已保存")
    except Exception as e:
        logger.error(f"[{__plugin_name__}] 保存配置失败: {e}")

# ================= 语音库管理 =================

def refresh_voice_map():
    """扫描文件系统，重建语音映射表"""
    global VOICE_MAP
    VOICE_MAP = {}
    
    # 1. 扫描插件自带的 voices 目录
    local_dir = PLUGIN_PATH / "voices"
    if local_dir.exists():
        for file in local_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                VOICE_MAP[file.stem] = str(file)
    
    # 2. 扫描用户添加的 extra_voices 目录
    if EXTRA_VOICE_DIR and EXTRA_VOICE_DIR.exists():
        pool = CONFIG.get("extra_voice_pool", [])
        for file in EXTRA_VOICE_DIR.iterdir():
            if file.is_file() and file.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                key = file.stem
                # 策略：如果池子为空，视为允许所有；否则只允许池子里的
                if not pool or key in pool:
                    VOICE_MAP[key] = str(file)
    
    logger.info(f"[{__plugin_name__}] 语音库已刷新，共 {len(VOICE_MAP)} 条语音")

# ================= 工具函数 =================

async def download_file(url: str, save_path: Path) -> bool:
    """异步下载文件"""
    try:
        # 设置 User-Agent 防止部分网站拦截
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    # 确保目录存在
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'wb') as f:
                        # 分块写入以防大文件内存溢出
                        async for chunk in resp.content.iter_chunked(1024):
                            f.write(chunk)
                    return True
                else:
                    logger.error(f"[{__plugin_name__}] 下载失败，状态码: {resp.status}")
                    return False
    except Exception as e:
        logger.error(f"[{__plugin_name__}] 下载异常: {e}")
        return False

def check_permission(event: AstrMessageEvent) -> bool:
    """检查用户是否有管理权限"""
    mode = CONFIG.get("admin_mode", "whitelist")
    
    sender_id = event.get_sender_id()
    nickname = event.get_sender_name()
    
    # 获取管理员列表 (兼容不同版本的 AstrBot)
    admin_ids = []
    try:
        # 尝试从 context 获取 (如果 event 有 context 属性)
        if hasattr(event, 'context') and hasattr(event.context, 'get_admin_ids'):
            admin_ids = event.context.get_admin_ids()
        # 某些版本直接在 event 上
        elif hasattr(event, 'get_admin_ids'):
            admin_ids = event.get_admin_ids()
    except Exception:
        pass
    
    # 模式判断
    if mode == "all":
        return True
    if mode == "admin":
        return sender_id in admin_ids
    
    # whitelist 模式
    allow_list = CONFIG.get("admin_whitelist", [])
    return (sender_id in allow_list) or (nickname in allow_list) or (sender_id in admin_ids)

def sanitize_filename(name: str) -> str:
    """清理文件名，只保留安全字符"""
    # 只保留字母、数字、中文、下划线、中划线
    safe_name = re.sub(r'[^\w\u4e00-\u9fa5_-]', '', name)
    return safe_name if safe_name else "unnamed"

# ================= 核心逻辑 =================

async def handle_message(event: AstrMessageEvent):
    """消息统一入口"""
    message_chain = event.get_message_chain()
    text = message_chain.text().strip()
    
    if not text:
        return

    # --- 1. 命令处理 ---
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        args_list = args.split() if args else []

        # === /voice.add ===
        if cmd == "/voice.add":
            if not check_permission(event):
                await event.send("❌ 权限不足：仅限管理员或白名单用户添加语音。")
                return
            
            ref_msg = event.get_message_ref()
            if not ref_msg:
                await event.send("❌ 用法错误：请**引用**一条语音消息，然后发送 `/voice.add 关键词`")
                return
            
            if not args_list:
                await event.send("❌ 请指定关键词，例如：`/voice.add 早上好`")
                return
            
            keyword = args_list[0]
            safe_name = sanitize_filename(keyword)
            
            if not safe_name:
                await event.send("❌ 关键词无效，请使用中文、字母或数字。")
                return

            # 解析引用消息中的文件
            file_url = None
            file_ext = "mp3"
            ref_chain = ref_msg.get_message_chain()
            
            for comp in ref_chain:
                ctype = getattr(comp, 'type', '')
                # 匹配语音、文件、录音类型
                if ctype in ['voice', 'record', 'file'] and hasattr(comp, 'url') and comp.url:
                    file_url = comp.url
                    # 尝试获取扩展名
                    if hasattr(comp, 'name') and comp.name and '.' in comp.name:
                        file_ext = comp.name.split('.')[-1]
                    elif '.' in file_url:
                        # 去除 URL 参数
                        clean_url = file_url.split('?')[0]
                        file_ext = clean_url.split('.')[-1]
                    break
            
            if not file_url:
                await event.send("❌ 未能在引用的消息中找到语音文件。")
                return

            # 构建保存路径
            filename = f"{safe_name}.{file_ext}"
            save_path = EXTRA_VOICE_DIR / filename
            
            logger.info(f"[{__plugin_name__}] 正在下载语音: {filename}")
            
            if await download_file(file_url, save_path):
                # ✅ 关键步骤：更新配置并持久化
                pool = CONFIG.get("extra_voice_pool", [])
                if safe_name not in pool:
                    pool.append(safe_name)
                    CONFIG["extra_voice_pool"] = pool
                    save_config()  # <--- 写入磁盘
                
                refresh_voice_map() # 刷新内存
                await event.send(f"✅ 语音 `{safe_name}` 添加成功！\n已永久保存至配置文件，重启后有效。")
            else:
                await event.send("❌ 语音文件下载失败，请检查链接或网络。")
            return

        # === /voice.delete ===
        if cmd == "/voice.delete":
            if not check_permission(event):
                await event.send("❌ 权限不足。")
                return
            if not args_list:
                await event.send("❌ 用法：`/voice.delete 关键词`")
                return
            
            name = args_list[0]
            target_file = None
            
            # 只在 extra_voices 中查找
            if EXTRA_VOICE_DIR.exists():
                for f in EXTRA_VOICE_DIR.iterdir():
                    if f.stem == name:
                        target_file = f
                        break
            
            if target_file:
                try:
                    target_file.unlink() # 删除文件
                    
                    # 从配置池中移除
                    pool = CONFIG.get("extra_voice_pool", [])
                    if name in pool:
                        pool.remove(name)
                        CONFIG["extra_voice_pool"] = pool
                        save_config()
                    
                    refresh_voice_map()
                    await event.send(f"🗑️ 语音 `{name}` 已删除。")
                except Exception as e:
                    await event.send(f"❌ 删除文件失败: {e}")
            else:
                await event.send(f"❌ 未找到名为 `{name}` 的用户自定义语音。")
            return

        # === /voice.list ===
        if cmd == "/voice.list":
            page = 1
            if args_list and args_list[0].isdigit():
                page = int(args_list[0])
            
            keys = sorted(VOICE_MAP.keys())
            total = len(keys)
            per_page = 20
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            if page < 1: page = 1
            if page > total_pages: page = total_pages
            
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            current_keys = keys[start_idx:end_idx]
            
            msg = f"📄 **语音列表** (第 {page}/{total_pages} 页，共 {total} 条)\n\n"
            if not current_keys:
                msg += "(暂无语音)"
            else:
                for k in current_keys:
                    # 标记是自带还是用户添加
                    source = "🔒" if k not in CONFIG.get("extra_voice_pool", []) and EXTRA_VOICE_DIR and (EXTRA_VOICE_DIR / f"{k}.mp3").exists() else "🔓"
                    # 简单标记：如果在 extra_voices 目录且不在 pool (理论上不会发生)，或者是 pool 里的
                    is_user = k in CONFIG.get("extra_voice_pool", [])
                    tag = "🟢" if is_user else "🔵"
                    msg += f"{tag} `{k}`\n"
            
            if total_pages > 1:
                msg += f"\n💡 提示：使用 `/voice.list {page+1}` 查看下一页"
            
            await event.send(msg)
            return

        # === /voice.reload ===
        if cmd == "/voice.reload":
            if not check_permission(event):
                await event.send("❌ 权限不足。")
                return
            refresh_voice_map()
            await event.send("🔄 语音库已重新加载。")
            return

        # === /voice.help ===
        if cmd == "/voice.help":
            help_text = (
                f"🌸 **{__plugin_name__} 帮助文档**\n\n"
                f"🔹 **触发方式**: {CONFIG.get('trigger_mode', 'direct')}\n"
                f"   - `direct`: 直接发送关键词 (如 `早安`)\n"
                f"   - `prefix`: 发送 `#voice 关键词`\n\n"
                f"🔹 **管理命令** (需权限):\n"
                f"   - `/voice.add 关键词`: 引用语音消息添加\n"
                f"   - `/voice.delete 关键词`: 删除用户语音\n"
                f"   - `/voice.list [页码]`: 查看列表\n"
                f"   - `/voice.reload`: 重载语音库\n"
                f"   - `/voice.check`: 检查当前权限"
            )
            await event.send(help_text)
            return
            
        # === /voice.check ===
        if cmd == "/voice.check":
            is_ok = check_permission(event)
            status = "✅ 拥有权限" if is_ok else "❌ 无权限"
            await event.send(f"当前用户权限状态：{status}\n模式：{CONFIG.get('admin_mode')}")
            return

    # --- 2. 语音触发逻辑 ---
    trigger_mode = CONFIG.get("trigger_mode", "direct")
    keyword = text
    
    # 前缀模式处理
    if trigger_mode == "prefix":
        if keyword.startswith("#voice "):
            keyword = keyword[7:].strip()
        else:
            return  # 非前缀且不匹配，直接忽略
    
    # 匹配并发送
    if keyword in VOICE_MAP:
        file_path = VOICE_MAP[keyword]
        if os.path.exists(file_path):
            try:
                # 发送文件 (语音)
                await event.send_file(file_path)
            except Exception as e:
                logger.error(f"[{__plugin_name__}] 发送语音失败: {e}")
                await event.send(f"⚠️ 语音文件存在，但发送失败：{str(e)}")
        else:
            # 文件丢失，从内存移除
            logger.warning(f"[{__plugin_name__}] 语音文件丢失: {file_path}")
            del VOICE_MAP[keyword]
            # 如果是在池子里的，也建议从池子移除并保存，防止下次报错
            if keyword in CONFIG.get("extra_voice_pool", []):
                CONFIG["extra_voice_pool"].remove(keyword)
                save_config()

# ================= 插件入口 =================

def init_plugin(context):
    """
    AstrBot v4+ 标准插件入口函数
    框架会自动调用此函数来初始化插件
    """
    global PLUGIN_PATH, DATA_DIR, EXTRA_VOICE_DIR
    
    PLUGIN_PATH = Path(__file__).parent
    logger.info(f"[{__plugin_name__}] 正在初始化...")
    
    # 1. 确定数据目录
    # 优先使用框架提供的数据目录， fallback 到插件目录下的 data 文件夹
    try:
        DATA_DIR = context.get_data_dir()
        EXTRA_VOICE_DIR = DATA_DIR / "extra_voices"
    except AttributeError:
        # 兼容旧版或特定环境
        DATA_DIR = PLUGIN_PATH / "data"
        EXTRA_VOICE_DIR = DATA_DIR / "extra_voices"
        logger.warning(f"[{__plugin_name__}] 无法获取框架数据目录，使用插件本地目录: {DATA_DIR}")
    
    # 确保目录存在
    EXTRA_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    
    # 2. 加载配置
    load_config()
    
    # 3. 构建语音库
    refresh_voice_map()
    
    # 4. 注册消息监听器
    # 这是 v4+ 的核心：将 handle_message 函数注册为全局消息处理器
    context.register_event_listener(handle_message)
    
    logger.info(f"[{__plugin_name__}] 初始化完成。当前语音数：{len(VOICE_MAP)}")
