from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import re
import random
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter, MessageChain
from astrbot.api.message_components import Record, Reply, Image as AstrImage
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

ALLOWED_EXT = {".mp3", ".wav", ".ogg", ".silk", ".amr"}
PAGE_SIZE = 15
IMAGE_PAGE_SIZE = 40          # 图片模式每页显示数量
FONT_SIZE = 28
IMAGE_WIDTH = 1360
IMAGE_BG_COLOR_TOP = (252, 248, 255)
IMAGE_BG_COLOR_BOTTOM = (244, 249, 255)
IMAGE_TEXT_COLOR = (44, 51, 74)


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
    plugin: Any = None

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        if not self.plugin or getattr(self.plugin, "trigger_mode", None) != "llm":
            return "当前未开启 LLM 触发模式，本工具暂不可用。"
        if not self.plugin.voice_map:
            return "当前没有可用语音。"
        names = sorted(self.plugin.voice_map.keys())
        return "当前可用语音名称列表：\n" + "\n".join(names)


@dataclass
class AiriSearchVoicesTool(FunctionTool[AstrAgentContext]):
    """根据关键词筛选语音名称。"""
    name: str = "airi_search_voices"
    description: str = "根据用户给出的关键词，在本插件的语音库中筛选匹配的语音名称。"
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
    plugin: Any = None

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        if not self.plugin or getattr(self.plugin, "trigger_mode", None) != "llm":
            return "当前未开启 LLM 触发模式，本工具暂不可用。"
        if not self.plugin.voice_map:
            return "当前没有可用语音。"
        keyword = (kwargs.get("keyword") or "").strip()
        if not keyword:
            return "请提供要搜索的语音关键词。"
        keyword_lower = keyword.lower()
        matched = [
            name for name in self.plugin.voice_map.keys() if keyword_lower in name.lower()
        ]
        if not matched:
            return f"未找到包含「{keyword}」的语音名称。"
        matched.sort()
        return f"根据关键词「{keyword}」筛选到的语音名称：\n" + "\n".join(matched)


@dataclass
class AiriSendVoiceTool(FunctionTool[AstrAgentContext]):
    """根据指定名称直接向当前会话发送语音。"""
    name: str = "airi_send_voice"
    description: str = "根据指定的语音名称，直接向当前会话发送对应的语音消息。"
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
    plugin: Any = None

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        if not self.plugin or getattr(self.plugin, "trigger_mode", None) != "llm":
            return "当前未开启 LLM 触发模式，本工具暂不可用。"
        if not self.plugin.voice_map:
            return "当前没有可用语音。"
        name = (kwargs.get("name") or "").strip()
        if not name:
            return "请提供要发送的语音名称。"
        path = self.plugin.voice_map.get(name)
        if not path:
            return f"语音「{name}」不存在，请先使用列出/搜索工具确认可用名称。"
        try:
            agent_ctx = context.context.context
            event = context.context.event
        except Exception:
            agent_ctx = None
            event = None
        if agent_ctx is None or event is None:
            return f"无法获取当前会话上下文，未能发送语音「{name}」。"
        try:
            await agent_ctx.send_message(
                event.unified_msg_origin,
                MessageChain([Record.fromFileSystem(path)]),
            )
            logger.debug(f"[AiriVoice] LLM 工具发送语音：'{name}' → {path}")
            return ""
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
    "2.4",
    "https://github.com/Lidure/astrbot_plugin_airi_voice",
)
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir = StarTools.get_data_dir("astrbot_plugin_airi_voice")
        self.user_added_dir = self.data_dir / "user_added"
        self.user_added_dir.mkdir(parents=True, exist_ok=True)
        self.extra_voice_dir = self.data_dir / "extra_voices"
        self.extra_voice_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[AiriVoice] 数据目录：{self.data_dir}")

        self.config = config or {}
        self.trigger_mode = self.config.get("trigger_mode", "direct")
        if self.trigger_mode not in {"prefix", "direct", "llm"}:
            logger.warning(f"[AiriVoice] 无效 trigger_mode，强制使用 direct")
            self.trigger_mode = "direct"

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

        self.llm_select_mode = self.config.get("llm_select_mode", "list")
        if self.llm_select_mode not in {"list", "keyword"}:
            logger.warning(f"[AiriVoice] 无效 llm_select_mode，强制使用 list")
            self.llm_select_mode = "list"

        self.auto_reply_voice_enabled = self.config.get("auto_reply_voice_on_bot_message", False)
        self.list_as_image = self.config.get("list_as_image", False)   # ← 新增

        self.voice_map: Dict[str, str] = {}
        self.sorted_keys: List[str] = []

        self._load_local_voices()
        self._load_user_added_voices()
        self._load_web_voices(self.config)
        self._update_sorted_keys()

        self.last_pool_len = len(self.config.get("extra_voice_pool", []))

        if self.trigger_mode == "llm":
            llm_tools = []
            if self.llm_select_mode == "list":
                llm_tools.append(AiriListAllVoicesTool(plugin=self))
            else:
                llm_tools.append(AiriSearchVoicesTool(plugin=self))
            llm_tools.append(AiriSendVoiceTool(plugin=self))
            try:
                self.context.add_llm_tools(*llm_tools)
                logger.info(f"[AiriVoice] 已为 LLM 注册 {len(llm_tools)} 个语音工具，模式：{self.llm_select_mode}")
            except Exception as e:
                logger.error(f"[AiriVoice] 注册 LLM 工具失败：{e}")

        if self.auto_reply_voice_enabled:
            logger.info("[AiriVoice] 已启用 bot 回复自动追加语音功能")

        logger.info(f"[AiriVoice] 初始化完成，共 {len(self.voice_map)} 个语音，权限模式：{self.admin_mode}，列表图片模式：{'开启' if self.list_as_image else '关闭'}")

    # ==================== 原有辅助方法（未修改） ====================

    def _get_user_id(self, event: AstrMessageEvent) -> Optional[str]:
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
        for seg in event.get_messages():
            if isinstance(seg, Reply):
                try:
                    return int(seg.id)
                except (ValueError, TypeError):
                    pass
        return None

    async def _get_audio_url(self, event: AstrMessageEvent) -> Optional[str]:
        # ...（保持你原来的实现不变）
        chain = event.get_messages()
        url = None
        def extract_media_url(seg):
            url_ = (getattr(seg, "url", None) or getattr(seg, "file", None) or getattr(seg, "path", None))
            return url_ if url_ and str(url_).startswith("http") else None

        reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
        if reply_seg and hasattr(reply_seg, 'chain') and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Record):
                    url = extract_media_url(seg)
                    if url: break

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
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                return await response.read()
        except Exception as e:
            logger.error(f"[AiriVoice] 下载音频失败：{e}")
            return None

    def _get_file_ext_from_url(self, url: str) -> str:
        url_lower = url.lower()
        if ".wav" in url_lower: return ".wav"
        elif ".ogg" in url_lower: return ".ogg"
        elif ".silk" in url_lower: return ".silk"
        elif ".amr" in url_lower: return ".amr"
        return ".mp3"

    def _update_sorted_keys(self):
        self.sorted_keys = sorted(self.voice_map.keys())

    # === 图像渲染辅助函数 ===
    def _load_image_font(self, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
        candidates = [
            "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
            "msyhbd.ttc" if bold else "msyh.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for p in candidates:
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _fit_text(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return text
        ell = "…"
        s = text
        while s:
            s = s[:-1]
            cand = s + ell
            if draw.textbbox((0, 0), cand, font=font)[2] <= max_width:
                return cand
        return ell

    def _wrap_text_lines(self, draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
        lines: List[str] = []
        for para in text.splitlines() or [""]:
            if not para:
                lines.append("")
                continue
            cur = ""
            for ch in para:
                cand = cur + ch
                if draw.textbbox((0, 0), cand, font=font)[2] <= max_width:
                    cur = cand
                else:
                    if cur:
                        lines.append(cur)
                    cur = ch
            if cur:
                lines.append(cur)
        return lines

    def _fill_vertical_gradient(self, img: Image.Image, top_color, bottom_color) -> None:
        w, h = img.size
        draw = ImageDraw.Draw(img)
        for y in range(h):
            r = y / max(1, h - 1)
            color = tuple(int(top_color[i] * (1 - r) + bottom_color[i] * r) for i in range(3))
            draw.line((0, y, w, y), fill=color)

    def _fill_pastel_gradient(self, img: Image.Image, colors: List[tuple]) -> None:
        w, h = img.size
        draw = ImageDraw.Draw(img)
        if len(colors) < 2:
            self._fill_vertical_gradient(img, colors[0], colors[0])
            return
        segments = len(colors) - 1
        for y in range(h):
            t = y / max(1, h - 1)
            seg = min(segments - 1, int(t * segments))
            local_t = t * segments - seg
            c1 = colors[seg]
            c2 = colors[seg + 1]
            color = tuple(int(c1[i] * (1 - local_t) + c2[i] * local_t) for i in range(3))
            draw.line((0, y, w, y), fill=color)

    def _load_local_voices(self):
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

    # ==================== 新增：图片生成方法（现代两栏样式） ====================
    def _create_voice_list_image(self, page: int = 1) -> Path:
        total = len(self.sorted_keys)
        total_pages = max(1, (total + IMAGE_PAGE_SIZE - 1) // IMAGE_PAGE_SIZE)
        page = max(1, min(page, total_pages))

        start = (page - 1) * IMAGE_PAGE_SIZE
        page_keys = self.sorted_keys[start:start + IMAGE_PAGE_SIZE]

        columns = 2
        padding_x = 68
        gap_x = 24
        gap_y = 16
        header_height = 160
        footer_height = 94
        card_height = 88
        content_width = IMAGE_WIDTH - padding_x * 2
        card_w = (content_width - gap_x) // 2
        rows = max(1, (len(page_keys) + columns - 1) // columns)
        h = header_height + rows * card_height + (rows - 1) * gap_y + footer_height

        img = Image.new("RGBA", (IMAGE_WIDTH, h), (255, 255, 255, 255))
        self._fill_pastel_gradient(img, [(255, 244, 249), (255, 250, 239), (240, 248, 255)])
        d = ImageDraw.Draw(img)

        accent = [(252, 168, 206), (142, 189, 255), (117, 225, 212), (202, 153, 255)]

        # transparent header with subtle outline
        header = Image.new("RGBA", (IMAGE_WIDTH, h), (0, 0, 0, 0))
        hd = ImageDraw.Draw(header)
        hd.rounded_rectangle((38, 30, IMAGE_WIDTH - 38, 150), radius=36, fill=(255, 255, 255, 0), outline=(255, 255, 255, 110), width=2)
        img = Image.alpha_composite(img, header)
        d = ImageDraw.Draw(img)

        tf = self._load_image_font(36, bold=True)
        sf = self._load_image_font(20)
        bf = self._load_image_font(26, bold=True)
        ff = self._load_image_font(22)
        hf = self._load_image_font(18)

        d.text((70, 42), "AiriVoice 语音列表", font=tf, fill=(30, 41, 59))
        d.text((70, 94), f"第 {page}/{total_pages} 页 · 共 {total} 个语音", font=sf, fill=(106, 122, 147))

        d.rounded_rectangle((IMAGE_WIDTH - 392, 50, IMAGE_WIDTH - 244, 98), radius=24, fill=(255, 240, 245))
        d.rounded_rectangle((IMAGE_WIDTH - 230, 50, IMAGE_WIDTH - 64, 98), radius=24, fill=(235, 248, 255))
        d.text((IMAGE_WIDTH - 376, 60), "总数", font=sf, fill=(101, 116, 139))
        d.text((IMAGE_WIDTH - 296, 58), str(total), font=self._load_image_font(20, bold=True), fill=(245, 99, 170))
        d.text((IMAGE_WIDTH - 214, 60), "页码", font=sf, fill=(101, 116, 139))
        d.text((IMAGE_WIDTH - 142, 58), f"{page}/{total_pages}", font=self._load_image_font(20, bold=True), fill=(14, 165, 233))

        for i, name in enumerate(page_keys):
            r = i // 2
            c = i % 2
            x1 = padding_x + c * (card_w + gap_x)
            y1 = 174 + r * (card_height + gap_y)
            x2 = x1 + card_w
            y2 = y1 + card_height
            ac = accent[i % 4]
            d.rounded_rectangle((x1 + 3, y1 + 5, x2 + 3, y2 + 5), radius=28, fill=(255, 255, 255, 72))
            d.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(255, 255, 255, 255), outline=(223, 228, 241, 255), width=1)
            d.rounded_rectangle((x1, y1, x1 + 6, y2), radius=6, fill=ac)
            # try to load user-provided small badge (psc.png) and paste with highlight
            try:
                badge_path = self.plugin_dir / "psc.png"
                with Image.open(badge_path) as _bi:
                    badge_img = _bi.convert("RGBA")
                    badge_size = 44
                    badge_resized = badge_img.resize((badge_size, badge_size), Image.LANCZOS)
                    # center on previous bubble center (keep visual alignment)
                    center_x = x1 + 38
                    center_y = y1 + 41
                    paste_x = int(center_x - badge_size / 2)
                    paste_y = int(center_y - badge_size / 2)
                    # paste badge (no outer glow)
                    img.paste(badge_resized, (paste_x, paste_y), badge_resized)
            except Exception:
                # fallback to colored bubble if badge missing or loading fails (solid)
                d.ellipse((x1 + 16, y1 + 17, x1 + 60, y1 + 61), fill=(ac[0], ac[1], ac[2], 255))
            d.text((x1 + 72, y1 + 20), name, font=bf, fill=IMAGE_TEXT_COLOR)
            d.text((x1 + 72, y1 + 50), "直接输入关键词即可发送", font=hf, fill=(124, 138, 161))

        footer_y = h - footer_height + 10
        d.rounded_rectangle((34, footer_y + 4, IMAGE_WIDTH - 34, h - 14), radius=24, fill=(255, 255, 255, 74))
        d.rounded_rectangle((34, footer_y, IMAGE_WIDTH - 34, h - 18), radius=24, fill=(255, 255, 255, 248), outline=(223, 228, 241, 255), width=1)
        d.text((68, footer_y + 18), "直接输入语音名称即可发送 · /voice.list [页码] 可翻页", font=ff, fill=(106, 122, 147))

        if total_pages > 1:
            nav_parts = []
            if page > 1:
                nav_parts.append(f"上一页 /voice.list {page - 1}")
            if page < total_pages:
                nav_parts.append(f"下一页 /voice.list {page + 1}")
            nav_text = " · ".join(nav_parts)
            nav_box = d.textbbox((0, 0), nav_text, font=ff)
            nav_width = nav_box[2] - nav_box[0]
            d.text((IMAGE_WIDTH - nav_width - 68, footer_y + 18), nav_text, font=ff, fill=(245, 99, 170))

        save_path = self.data_dir / f"voice_list_p{page}.png"
        img.save(save_path)
        return save_path

    def _create_help_image(self, is_admin: bool) -> Path:
        width = IMAGE_WIDTH
        padding_x = 48
        card_x = 48
        card_width = width - padding_x * 2
        top_y = 176
        gap_y = 18

        title_font = self._load_image_font(40, bold=True)
        subtitle_font = self._load_image_font(20)
        section_title_font = self._load_image_font(25, bold=True)
        body_font = self._load_image_font(20)
        footer_font = self._load_image_font(18)

        sections = [
            (
                "快速说明",
                [
                    "直接输入语音关键词即可发送对应语音。",
                    "支持本地 voices/、网页上传、/voice.add 三种添加方式。",
                ],
                (244, 114, 182),
            ),
            (
                "触发模式",
                [
                    "direct（默认）：直接输入关键词触发。",
                    "prefix：需使用 #voice 关键词 触发。",
                    "llm：由大模型通过工具调用。",
                ],
                (96, 165, 250),
            ),
            (
                "可用命令",
                [
                    "/voice.list [页码] - 查看可用语音列表",
                ],
                (96, 165, 250),
            ),

            # transparent header with subtle outline
            header = Image.new("RGBA", (IMAGE_WIDTH, h), (0, 0, 0, 0))
            hd = ImageDraw.Draw(header)
            hd.rounded_rectangle((38, 30, IMAGE_WIDTH - 38, 150), radius=36, fill=(255, 255, 255, 0), outline=(255, 255, 255, 110), width=2)
            img = Image.alpha_composite(img, header)
        if is_admin:
            sections.append(("管理员命令", [
                "/voice.add 名字 - 引用语音消息添加新语音",
                "/voice.delete 名字 - 删除通过 .add 添加的语音",
                "/voice.reload - 重新加载语音列表",
                "/voice.check - 查看当前用户权限",
            ], (168, 85, 247)))

        sections.append(("图片列表提示", [
            "可在插件配置中开启 list_as_image，让 /voice.list 以图片形式展示。",
            "分页可直接输入 /voice.list 2、/voice.list 3 继续翻页。",
        ], (251, 191, 36)))

        # measure heights
        temp_img = Image.new("RGBA", (width, 1200), IMAGE_BG_COLOR_TOP)
        temp_draw = ImageDraw.Draw(temp_img)
        card_line_height = 30
        section_title_height = 32
        card_padding_y = 24

        card_heights: List[int] = []
        wrapped_sections: List[List[str]] = []
        for _, items, _ in sections:
            wrapped_lines: List[str] = []
            for item in items:
        footer_height = 84
                d.rounded_rectangle((x1 + 3, y1 + 5, x2 + 3, y2 + 5), radius=28, fill=(255, 255, 255, 72))
                d.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=(255, 255, 255, 255), outline=(223, 228, 241, 255), width=1)
                d.rounded_rectangle((x1, y1, x1 + 6, y2), radius=6, fill=ac)
                d.ellipse((x1 + 22, y1 + 25, x1 + 54, y1 + 57), fill=(ac[0], ac[1], ac[2], 44))
                d.text((x1 + 72, y1 + 20), name, font=bf, fill=IMAGE_TEXT_COLOR)
                d.text((x1 + 72, y1 + 50), "直接输入关键词即可发送", font=hf, fill=(124, 138, 161))
        gap_between_cards = gap_y
        height = header_height + sum(card_heights) + gap_between_cards * (len(card_heights) - 1) + footer_height

        img = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        self._fill_pastel_gradient(img, [(255, 244, 249), (255, 250, 239), (240, 248, 255)])

        draw = ImageDraw.Draw(img)

        glass_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glass_draw = ImageDraw.Draw(glass_layer)
        header_box = (34, 24, width - 34, 146)
        shadow_box = (header_box[0] + 4, header_box[1] + 6, header_box[2] + 4, header_box[3] + 6)
        glass_draw.rounded_rectangle(shadow_box, radius=36, fill=(255, 255, 255, 0))
        glass_draw.rounded_rectangle(header_box, radius=36, fill=(255, 255, 255, 0), outline=(255, 255, 255, 110), width=2)
        img = Image.alpha_composite(img, glass_layer)
        draw = ImageDraw.Draw(img)

        draw.text((70, 42), "AiriVoice 使用帮助", font=title_font, fill=(30, 41, 59))
        draw.text((70, 94), "一张图快速看懂如何使用、分页和管理语音", font=subtitle_font, fill=(106, 122, 147))

        pill_y = 50
        pill_specs = [
            ("状态", "已就绪", (255, 241, 246), (245, 99, 170), 210),
            ("模式", self.trigger_mode, (236, 249, 255), (70, 154, 244), 168),
        ]

        x_right = width - 68
        gap_between = 14
        pill_height = 48
        for label, value, pill_bg, pill_fg, pill_w in reversed(pill_specs):
            x0 = x_right - pill_w
            x1 = x_right
            value_font = self._load_image_font(18, bold=True)
            value_box = draw.textbbox((0, 0), str(value), font=value_font)
            label_box = draw.textbbox((0, 0), label, font=subtitle_font)
            label_h = label_box[3] - label_box[1]
            value_h = value_box[3] - value_box[1]
            value_w = value_box[2] - value_box[0]
            draw.rounded_rectangle((x0, pill_y, x1, pill_y + pill_height), radius=24, fill=pill_bg)
            draw.text((x0 + 12, pill_y + (pill_height - label_h) / 2 - 1), label, font=subtitle_font, fill=(101, 116, 139))
            draw.text((x1 - value_w - 12, pill_y + (pill_height - value_h) / 2 - 1), str(value), font=value_font, fill=pill_fg)
            x_right = x0 - gap_between

        section_y = top_y
        section_bg_colors = [(255, 255, 255, 255)] * 5

        for index, ((section_title, _, accent), wrapped_lines, card_height, card_bg) in enumerate(zip(sections, wrapped_sections, card_heights, section_bg_colors)):
            y1 = section_y
            y2 = y1 + card_height
            # cleaner card, remove heavy shadow and full-height stripe
            draw.rounded_rectangle((card_x, y1, card_x + card_width, y2), radius=28, fill=(255, 255, 255, 255), outline=(223, 228, 241, 255), width=1)
            # try to load user-provided larger badge (psc2.png) and paste with highlight
            try:
                badge_path2 = self.plugin_dir / "psc2.png"
                with Image.open(badge_path2) as _bi2:
                    badge_img2 = _bi2.convert("RGBA")
                    badge_size2 = 44
                    badge_resized2 = badge_img2.resize((badge_size2, badge_size2), Image.LANCZOS)
                    # enlarge and nudge a bit to keep padding consistent
                    paste_x = card_x + 18
                    paste_y = y1 + 18
                    img.paste(badge_resized2, (paste_x, paste_y), badge_resized2)
            except Exception:
                badge_cx = card_x + 40
                badge_cy = y1 + (card_height // 2)
                badge_r = 22
                draw.ellipse((badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r), fill=(accent[0], accent[1], accent[2], 255))
            icon_box = (card_x + 18, y1 + 18, card_x + 18 + badge_size2, y1 + 18 + badge_size2)
            draw.text((card_x + 70, y1 + 20), section_title, font=section_title_font, fill=(30, 41, 59))
            text_y = y1 + 64
            # use a colored bullet with ~80% opacity for better visibility
            bullet_fill = (accent[0], accent[1], accent[2], int(255 * 0.8))
            for line in wrapped_lines:
                if not line:
                    text_y += 8
                    continue
                dot_box = (card_x + 72, text_y + 10, card_x + 82, text_y + 20)
                draw.ellipse(dot_box, fill=bullet_fill)
                draw.text((card_x + 94, text_y), line, font=body_font, fill=IMAGE_TEXT_COLOR)
                text_y += card_line_height
            section_y = y2 + gap_between_cards

        footer_y = height - footer_height + 10
        draw.rounded_rectangle((34, footer_y + 4, width - 34, height - 14), radius=24, fill=(255, 255, 255, 74))
        draw.rounded_rectangle((34, footer_y, width - 34, height - 18), radius=24, fill=(255, 255, 255, 248), outline=(223, 228, 241, 255), width=1)
        draw.text((68, footer_y + 18), "直接输入语音名称即可发送 · /voice.list 可查看语音列表", font=footer_font, fill=(106, 122, 147))

        save_path = self.data_dir / "voice_help.png"
        img.save(save_path)
        return save_path

    # ==================== 指令（仅修改 list 和 help） ====================

    @filter.command("voice.list")
    async def list_voices(self, event: AstrMessageEvent):
        if not self.sorted_keys:
            yield event.plain_result("当前没有可用语音～\n将语音文件放入 voices/ 目录或通过网页上传")
            return

        args = (event.message_str or "").strip().split()
        page = max(1, int(args[1])) if len(args) > 1 and args[1].isdigit() else 1

        if self.list_as_image:
            img_path = self._create_voice_list_image(page)
            yield event.chain_result([AstrImage.fromFileSystem(str(img_path))])
        else:
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
                msg += "\n\n" + " | ".join(nav)
            yield event.plain_result(msg)

    @filter.command("voice.help")
    async def help(self, event: AstrMessageEvent):
        is_admin = self._check_admin(event)
        img_path = self._create_help_image(is_admin)
        yield event.chain_result([AstrImage.fromFileSystem(str(img_path))])

    # ==================== 以下所有方法完全保持不变 ====================

    @filter.regex(r"^\s*.+\s*$")
    async def voice_handler(self, event: AstrMessageEvent):
        # ... 你原来的完整代码（未做任何修改）
        text = (event.message_str or "").strip()
        if not text:
            return
        current_pool_len = len(self.config.get("extra_voice_pool", []))
        if current_pool_len > self.last_pool_len:
            logger.info("[AiriVoice] 检测到网页配置变化，自动刷新语音列表")
            self._load_web_voices(self.config)
            self._update_sorted_keys()
            self.last_pool_len = current_pool_len

        # 随机语音处理...
        if text.startswith("随机") and self.voice_map:
            if text in {"随机发条语音", "随机语音"}:
                name = random.choice(list(self.voice_map.keys()))
                matched_path = self.voice_map.get(name)
                if matched_path:
                    try:
                        yield event.chain_result([Record.fromFileSystem(matched_path)])
                        logger.debug(f"[AiriVoice] 随机发送语音（全局）：'{name}'")
                    except Exception as e:
                        logger.error(f"[AiriVoice] 随机发送失败 '{name}': {e}")
                        yield event.plain_result("语音发送失败")
                else:
                    yield event.plain_result("当前没有可用语音～")
                return

            m = re.match(r"^随机\s*(.+)$", text)
            if m:
                kw = m.group(1).strip()
                candidates = [name for name in self.voice_map.keys() if kw in name]
                if not candidates:
                    yield event.plain_result(f"未找到包含「{kw}」的语音")
                    return
                name = random.choice(candidates)
                matched_path = self.voice_map.get(name)
                if matched_path:
                    try:
                        yield event.chain_result([Record.fromFileSystem(matched_path)])
                    except Exception as e:
                        logger.error(f"[AiriVoice] 随机发送失败 '{name}': {e}")
                        yield event.plain_result("语音发送失败")
                return

        # 普通关键词处理...
        keyword = text
        if self.trigger_mode == "prefix":
            match = re.search(r"^#voice\s+(.+)", text, re.I)
            if not match:
                return
            keyword = match.group(1).strip()

        matched_path = self.voice_map.get(keyword)
        if matched_path:
            try:
                yield event.chain_result([Record.fromFileSystem(matched_path)])
                logger.debug(f"[AiriVoice] 发送语音：'{keyword}'")
            except FileNotFoundError as e:
                logger.error(f"[AiriVoice] 文件不存在 '{keyword}': {e}")
                yield event.plain_result("语音文件不存在")
            except Exception as e:
                logger.error(f"[AiriVoice] 发送失败 '{keyword}': {e}")
                yield event.plain_result("语音发送失败")

    @filter.command("voice.add")
    async def voice_add(self, event: AstrMessageEvent, name: str):
        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员使用")
            return
        if not self._get_reply_id(event):
            yield event.plain_result("❌ 请引用一条语音消息后再使用此命令")
            return
        if not name or name.strip() == "":
            yield event.plain_result("❌ 请提供语音名称，例如：/voice.add 打卡啦摩托")
            return
        name = name.strip()
        if name in self.voice_map:
            yield event.plain_result(f"⚠️ 语音「{name}」已存在，如需覆盖请先删除旧语音")
            return
        audio_url = await self._get_audio_url(event)
        if not audio_url:
            yield event.plain_result("❌ 未能从引用的消息中提取到音频，请确保引用的是语音消息")
            return
        logger.debug(f"[AiriVoice] 获取到音频 URL: {audio_url}")
        audio_data = await self._download_audio(audio_url)
        if not audio_data:
            yield event.plain_result("❌ 音频下载失败，请稍后重试")
            return
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
        if not self._check_admin(event):
            yield event.plain_result("❌ 权限不足：此命令仅限管理员使用")
            return
        if name not in self.voice_map:
            yield event.plain_result(f"❌ 语音「{name}」不存在")
            return
        file_path = Path(self.voice_map[name])
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
            msg += "\n\n" + " | ".join(nav)
        yield event.plain_result(msg)

    @filter.command("voice.reload")
    async def reload_voices(self, event: AstrMessageEvent):
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
        is_admin = self._check_admin(event)
        img_path = self._create_help_image(is_admin)
        yield event.chain_result([AstrImage.fromFileSystem(str(img_path))])

    @filter.command("voice.check")
    async def check_permission(self, event: AstrMessageEvent):
        is_admin = self._check_admin(event)
        user_id = self._get_user_id(event) or "未知"
        msg = f"🔐 权限检查\n\n"
        msg += f"用户 ID: {user_id}\n"
        msg += f"权限模式：{self.admin_mode}\n"
        msg += f"是否有权限：{'✅ 是' if is_admin else '❌ 否'}\n"
        if self.admin_mode == "whitelist" and not is_admin:
            msg += f"\n💡 提示：在 AstrBot 网页后台 → 插件配置 → admin_whitelist 中添加您的用户 ID"
        yield event.plain_result(msg)

    # ────────────────────────────────────────────────
    # 新功能：bot 回复自动追加语音（核心部分）
    # ────────────────────────────────────────────────

    @filter.on_decorating_result()
    async def on_bot_reply_auto_voice(self, event: AstrMessageEvent):
        if not self.auto_reply_voice_enabled:
            return

        result = event.get_result()
        if not result or not hasattr(result, "chain") or not result.chain:
            return

        text_parts = []
        has_record_already = False
        for seg in result.chain:
            if isinstance(seg, Record):
                has_record_already = True
            elif hasattr(seg, "text"):
                text_parts.append(str(getattr(seg, "text", "") or ""))
            elif isinstance(seg, str):
                text_parts.append(seg)

        text = "".join(text_parts).strip()
        if not text or has_record_already:
            return  # 已包含语音或无文本 → 不处理

        # 新增：过滤插件自己的命令回复，避免自我触发
        if "可用语音" in text or "第" in text and "页" in text or "/voice.list" in text:
            logger.debug("[AiriVoice-auto] 检测到 /voice.list 回复，跳过自动追加语音")
            return

        logger.debug(f"[AiriVoice-auto] bot 回复文本待检查: {text!r}")

        for keyword in self.sorted_keys:
            if keyword in text:
                path = self.voice_map.get(keyword)
                if path:
                    try:
                        result.chain.append(Record.fromFileSystem(path))
                        logger.info(
                            f"[AiriVoice-auto] 已追加语音 → 关键词: '{keyword}'  文件: {path}"
                        )
                        break  # 只追加一个，避免刷屏
                    except Exception as e:
                        logger.error(f"[AiriVoice-auto] 追加语音失败 '{keyword}': {e}")
