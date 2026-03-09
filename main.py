from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api import logger
from astrbot.core.star.star_tools import StarTools
from pathlib import Path
import re
from typing import Dict

@register("airi_voice", "lidure", "输入关键词发送对应语音（本地 + 网页上传）", "1.2", "https://github.com/你的用户名/astrbot_plugin_airi_voice")
class AiriVoice(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)

        self.plugin_dir = Path(__file__).parent
        self.voice_dir = self.plugin_dir / "voices"

        # 获取插件专用数据目录（模仿 pokepro）
        self.data_dir = Path(StarTools.get_data_dir("astrbot_plugin_airi_voice"))
        self.extra_voice_dir = self.data_dir / "extra_voices"
        self.extra_voice_dir.mkdir(parents=True, exist_ok=True)

        # 语音映射：关键词 → 绝对路径
        self.voice_map: Dict[str, str] = {}
        # 缓存排序后的关键词列表（用于 voice_list）
        self.sorted_keys: list[str] = []

        # 加载本地 voices
        self._load_local_voices()

        # 保存 config 用于 reload
        self.config = config

        # 加载网页配置语音
        self._load_web_voices(config)

        # 预编译正则（可选动态关键词匹配，但这里用前缀更安全）
        logger.info(f"[AiriVoice] 初始化完成，当前语音总数：{len(self.voice_map)} 个")

    def _load_local_voices(self):
        """扫描本地 voices/ 文件夹"""
        if not self.voice_dir.exists():
            self.voice_dir.mkdir(parents=True, exist_ok=True)
            logger.info("[AiriVoice] 已创建本地 voices 目录")

        count = 0
        for file_path in self.voice_dir.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in {'.mp3', '.wav', '.ogg', '.silk', '.amr'}:
                keyword = file_path.stem.strip()
                if keyword in self.voice_map:
                    logger.warning(f"[AiriVoice] 本地关键词冲突：'{keyword}' 已存在，将被覆盖")
                self.voice_map[keyword] = str(file_path)
                count += 1
                logger.debug(f"[AiriVoice] 本地加载：'{keyword}' → {file_path}")

        if count > 0:
            logger.info(f"[AiriVoice] 从本地 voices 加载 {count} 个语音")

        # 更新排序缓存
        self.sorted_keys = sorted(self.voice_map.keys())

    def _load_web_voices(self, config: dict = None):
        """从网页配置加载额外语音（相对路径）"""
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
                    logger.warning(f"[AiriVoice] 检测到非法路径尝试: {rel_path} → {abs_path}")
                    continue
            except Exception as e:
                logger.warning(f"[AiriVoice] 路径解析失败: {rel_path} - {e}")
                continue

            if abs_path.exists() and abs_path.is_file():
                keyword = abs_path.stem.strip()
                if keyword in self.voice_map:
                    logger.warning(f"[AiriVoice] 网页关键词冲突：'{keyword}' 已存在，将覆盖")
                self.voice_map[keyword] = str(abs_path)
                loaded += 1
                logger.info(f"[AiriVoice] 网页加载成功：'{keyword}' → {abs_path}")
            else:
                logger.warning(f"[AiriVoice] 网页文件不存在：{abs_path} (相对: {rel_path})")

        if loaded > 0:
            logger.info(f"[AiriVoice] 从网页配置加载 {loaded} 个额外语音")

        # 更新排序缓存
        self.sorted_keys = sorted(self.voice_map.keys())

    @filter.regex(r"^\s*/v\s+([^\s\u3000]+)\s*$")
    async def voice_handler(self, event: AstrMessageEvent):
        match = re.search(r"/v\s+(.+)", event.message_str.strip(), re.I)
        if not match:
            return

        text = match.group(1).strip()
        matched_path = self.voice_map.get(text)
        if matched_path is None:
            return

        try:
            logger.info(f"[AiriVoice] 触发语音：'{text}' → {matched_path}")
            chain = [Record.fromFileSystem(matched_path)]
            yield event.chain_result(chain)
        except Exception as e:
            logger.error(f"[AiriVoice] 发送失败 '{text}': {str(e)}", exc_info=True)
            yield event.plain_result(f"语音发送失败：{str(e)}")

    @filter.command("voice.reload")
    async def reload_voices(self, event: AstrMessageEvent):
        old_count = len(self.voice_map)

        # 清空并重新加载
        self.voice_map.clear()
        self._load_local_voices()
        if self.config:
            self._load_web_voices(self.config)

        new_count = len(self.voice_map)
        yield event.plain_result(
            f"语音列表已刷新！\n"
            f"之前 {old_count} 个 → 现在 {new_count} 个\n"
            f"网页上传的文件已重新加载\n"
            f"如果最近修改了网页配置，建议再发一次 /plugin reload"
        )

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
                nav += f" /voice_list {page-1} ← 上一页"
            if page < total_pages:
                nav += f" /voice_list {page+1} → 下一页"
            if nav:
                msg += f"\n{nav.strip()}"

        yield event.plain_result(msg)
