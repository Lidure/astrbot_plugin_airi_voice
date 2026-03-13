import os
import json
import aiohttp
import re
from pathlib import Path
from typing import Dict, Any, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

# ================= 插件元数据 =================
__plugin_name__ = "airi_voice"
__version__ = "2.6.2"
__author__ = "lidure"
__description__ = "爱理语音插件：支持关键词触发、引用添加语音、配置永久保存。"

# ================= 全局状态 =================
PLUGIN_PATH: Optional[Path] = None
DATA_DIR: Optional[Path] = None
EXTRA_VOICE_DIR: Optional[Path] = None
CONFIG: Dict[str, Any] = {}
VOICE_MAP: Dict[str, str] = {}

# ================= 配置管理 =================

def _get_config_path() -> Path:
    return PLUGIN_PATH / "config.json"

def _get_default_config() -> Dict[str, Any]:
    return {
        "extra_voice_pool": [],
        "trigger_mode": "direct",
        "admin_mode": "whitelist",
        "admin_whitelist": []
    }

def load_config():
    global CONFIG
    config_path = _get_config_path()
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                CONFIG = json.load(f)
            # 补全缺失的配置项
            default = _get_default_config()
            for key, value in default.items():
                if key not in CONFIG:
                    CONFIG[key] = value
        except Exception as e:
            logger.error(f"[{__plugin_name__}] 配置文件加载失败：{e}")
            CONFIG = _get_default_config()
    else:
        CONFIG = _get_default_config()
    
    save_config()

def save_config():
    config_path = _get_config_path()
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(CONFIG, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"[{__plugin_name__}] 保存配置失败：{e}")

# ================= 语音库管理 =================

def refresh_voice_map():
    global VOICE_MAP
    VOICE_MAP = {}
    
    # 扫描内置语音
    local_dir = PLUGIN_PATH / "voices"
    if local_dir.exists():
        for file in local_dir.iterdir():
            if file.is_file() and file.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                VOICE_MAP[file.stem] = str(file)
    
    # 扫描用户语音
    if EXTRA_VOICE_DIR and EXTRA_VOICE_DIR.exists():
        saved_pool = CONFIG.get("extra_voice_pool", [])
        for file in EXTRA_VOICE_DIR.iterdir():
            if file.is_file() and file.suffix.lower() in ['.mp3', '.wav', '.ogg', '.silk', '.amr']:
                key = file.stem
                if not saved_pool or key in saved_pool:
                    VOICE_MAP[key] = str(file)
    
    logger.info(f"[{__plugin_name__}] 语音库加载完成，共 {len(VOICE_MAP)} 条语音")

# ================= 工具函数 =================

async def download_file(url: str, save_path: Path) -> bool:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=30) as resp:
                if resp.status == 200:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024):
                            f.write(chunk)
                    return True
        return False
    except Exception as e:
        logger.error(f"[{__plugin_name__}] 下载失败：{e}")
        return False

def check_permission(event: AstrMessageEvent) -> bool:
    mode = CONFIG.get("admin_mode", "whitelist")
    sender_id = str(event.get_sender_id())
    nickname = str(event.get_sender_name())
    
    admin_ids = []
    try:
        if hasattr(event, 'context') and hasattr(event.context, 'get_admin_ids'):
            admin_ids = [str(x) for x in event.context.get_admin_ids()]
    except Exception:
        pass
    
    if mode == "all":
        return True
    if mode == "admin":
        return sender_id in admin_ids
    
    allow_list = [str(x) for x in CONFIG.get("admin_whitelist", [])]
    return sender_id in allow_list or nickname in allow_list or sender_id in admin_ids

def sanitize_filename(name: str) -> str:
    safe_name = re.sub(r'[^\w\u4e00-\u9fa5_-]', '', name)
    return safe_name if safe_name else "unnamed"

# ================= 消息处理 =================

async def handle_message(event: AstrMessageEvent):
    try:
        message_chain = event.get_message_chain()
        text = message_chain.text().strip()
    except Exception:
        return
    
    if not text:
        return

    # 命令处理
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd = parts[0] if len(parts) > 0 else ""
        args = parts[1] if len(parts) > 1 else ""
        args_list = args.split() if args else []

        # /voice.add
        if cmd == "/voice.add":
            if not check_permission(event):
                await event.send("❌ 权限不足")
                return
            
            ref_msg = event.get_message_ref()
            if not ref_msg:
                await event.send("❌ 请引用一条语音消息后使用此命令")
                return
            
            if len(args_list) == 0:
                await event.send("❌ 请指定关键词，如：/voice.add 早上好")
                return
            
            keyword = args_list[0]
            safe_name = sanitize_filename(keyword)
            
            if not safe_name:
                await event.send("❌ 关键词无效")
                return

            file_url = None
            file_ext = "mp3"
            ref_chain = ref_msg.get_message_chain()
            
            for comp in ref_chain:
                ctype = getattr(comp, 'type', '')
                if ctype in ['voice', 'record', 'file'] and hasattr(comp, 'url') and comp.url:
                    file_url = comp.url
                    if hasattr(comp, 'name') and comp.name and '.' in comp.name:
                        file_ext = comp.name.split('.')[-1]
                    elif '.' in file_url:
                        file_ext = file_url.split('?')[0].split('.')[-1]
                    break
            
            if not file_url:
                await event.send("❌ 未找到语音文件")
                return

            filename = f"{safe_name}.{file_ext}"
            save_path = EXTRA_VOICE_DIR / filename
            
            if await download_file(file_url, save_path):
                pool = CONFIG.get("extra_voice_pool", [])
                if safe_name not in pool:
                    pool.append(safe_name)
                    CONFIG["extra_voice_pool"] = pool
                    save_config()
                
                refresh_voice_map()
                await event.send(f"✅ 语音 `{safe_name}` 添加成功！")
            else:
                await event.send("❌ 下载失败")
            return

        # /voice.delete
        if cmd == "/voice.delete":
            if not check_permission(event):
                await event.send("❌ 权限不足")
                return
            if len(args_list) == 0:
                await event.send("❌ 用法：/voice.delete 关键词")
                return
            
            name = args_list[0]
            target_file = None
            
            if EXTRA_VOICE_DIR and EXTRA_VOICE_DIR.exists():
                for f in EXTRA_VOICE_DIR.iterdir():
                    if f.stem == name:
                        target_file = f
                        break
            
            if target_file:
                try:
                    target_file.unlink()
                    pool = CONFIG.get("extra_voice_pool", [])
                    if name in pool:
                        pool.remove(name)
                        CONFIG["extra_voice_pool"] = pool
                        save_config()
                    refresh_voice_map()
                    await event.send(f"🗑️ 语音 `{name}` 已删除")
                except Exception as e:
                    await event.send(f"❌ 删除失败：{e}")
            else:
                await event.send(f"❌ 未找到语音 `{name}`")
            return

        # /voice.list
        if cmd == "/voice.list":
            page = 1
            if len(args_list) > 0 and args_list[0].isdigit():
                page = int(args_list[0])
            
            keys = sorted(VOICE_MAP.keys())
            total = len(keys)
            per_page = 20
            total_pages = max(1, (total + per_page - 1) // per_page)
            
            if page < 1:
                page = 1
            if page > total_pages:
                page = total_pages
            
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            current_keys = keys[start_idx:end_idx]
            
            msg = f"📄 语音列表 (第 {page}/{total_pages} 页，共 {total} 条)\n\n"
            for k in current_keys:
                is_user = k in CONFIG.get("extra_voice_pool", [])
                tag = "🟢" if is_user else "🔵"
                msg += f"{tag} `{k}`\n"
            
            await event.send(msg)
            return

        # /voice.reload
        if cmd == "/voice.reload":
            if not check_permission(event):
                await event.send("❌ 权限不足")
                return
            refresh_voice_map()
            await event.send("🔄 已重载")
            return

        # /voice.help
        if cmd == "/voice.help":
            await event.send(
                f"🌸 Airi Voice 帮助\n\n"
                f"触发模式：{CONFIG.get('trigger_mode', 'direct')}\n"
                f"direct: 直接发送关键词\n"
                f"prefix: 发送 #voice 关键词\n\n"
                f"命令:\n"
                f"/voice.list - 查看列表\n"
                f"/voice.add 关键词 - 引用语音添加\n"
                f"/voice.delete 关键词 - 删除语音\n"
                f"/voice.reload - 重载\n"
                f"/voice.help - 帮助"
            )
            return

        # /voice.check
        if cmd == "/voice.check":
            is_ok = check_permission(event)
            await event.send(f"权限：{'✅ 有' if is_ok else '❌ 无'}")
            return

    # 语音触发
    trigger_mode = CONFIG.get("trigger_mode", "direct")
    keyword = text
    
    if trigger_mode == "prefix":
        if keyword.startswith("#voice "):
            keyword = keyword[7:].strip()
        else:
            return
    
    if keyword in VOICE_MAP:
        file_path = VOICE_MAP[keyword]
        if os.path.exists(file_path):
            try:
                await event.send_file(file_path)
            except Exception as e:
                logger.error(f"[{__plugin_name__}] 发送失败：{e}")

# ================= 插件入口 =================

def init_plugin(context):
    global PLUGIN_PATH, DATA_DIR, EXTRA_VOICE_DIR
    
    PLUGIN_PATH = Path(__file__).parent
    logger.info(f"[{__plugin_name__}] 初始化中...")
    
    try:
        DATA_DIR = context.get_data_dir()
    except Exception:
        DATA_DIR = PLUGIN_PATH / "data"
    
    EXTRA_VOICE_DIR = DATA_DIR / "extra_voices"
    EXTRA_VOICE_DIR.mkdir(parents=True, exist_ok=True)
    
    load_config()
    refresh_voice_map()
    
    context.register_event_listener(handle_message)
    
    logger.info(f"[{__plugin_name__}] 初始化完成")
