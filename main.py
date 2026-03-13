import aiohttp
import os
from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.message.components import Reply, Record


class AiriVoicePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.voices_dir = os.path.join(self.context.get_data_dir(), "voices")
        self.voice_list = []
        self._scan_voices()

    def _scan_voices(self):
        """扫描 voices 目录中的语音文件"""
        self.voice_list = []
        if os.path.exists(self.voices_dir):
            for file in os.listdir(self.voices_dir):
                if file.endswith(('.mp3', '.wav', '.ogg', '.silk', '.amr')):
                    name = os.path.splitext(file)[0]
                    self.voice_list.append(name)

    def _get_reply_id(self, event: AstrMessageEvent) -> int | None:
        """获取被引用消息的 ID"""
        for seg in event.get_messages():
            if isinstance(seg, Reply):
                return int(seg.id)
        return None

    async def _get_audio_url(self, event: AstrMessageEvent) -> str | None:
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

        # 遍历引用消息
        reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
        if reply_seg and reply_seg.chain:
            for seg in reply_seg.chain:
                if isinstance(seg, Record):
                    url = extract_media_url(seg)
                    if url:
                        break

        # 从原始引用消息中获取
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
                    logger.error(f"获取引用消息失败：{e}")

        return url

    async def _download_audio(self, url: str) -> bytes | None:
        """下载音频文件"""
        try:
            async with aiohttp.ClientSession() as client:
                response = await client.get(url)
                return await response.read()
        except Exception as e:
            logger.error(f"下载音频失败：{e}")
            return None

    @filter.command("voice.add")
    async def voice_add(self, event: AstrMessageEvent, name: str):
        """
        通过引用语音消息添加新语音
        用法：引用一条语音消息，然后发送 /voice.add 名字
        """
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
        if name in self.voice_list:
            yield event.plain_result(f"⚠️ 语音「{name}」已存在，如需覆盖请先删除旧语音")
            return

        # 获取音频 URL
        audio_url = await self._get_audio_url(event)
        if not audio_url:
            yield event.plain_result("❌ 未能从引用的消息中提取到音频，请确保引用的是语音消息")
            return

        logger.debug(f"获取到音频 URL: {audio_url}")

        # 下载音频
        audio_data = await self._download_audio(audio_url)
        if not audio_data:
            yield event.plain_result("❌ 音频下载失败，请稍后重试")
            return

        # 确保目录存在
        os.makedirs(self.voices_dir, exist_ok=True)

        # 确定文件扩展名（根据 URL 或默认 mp3）
        ext = ".mp3"
        if ".wav" in audio_url.lower():
            ext = ".wav"
        elif ".ogg" in audio_url.lower():
            ext = ".ogg"
        elif ".silk" in audio_url.lower():
            ext = ".silk"
        elif ".amr" in audio_url.lower():
            ext = ".amr"

        # 保存文件
        file_path = os.path.join(self.voices_dir, f"{name}{ext}")
        try:
            with open(file_path, "wb") as f:
                f.write(audio_data)
            
            # 刷新语音列表
            self._scan_voices()
            
            yield event.plain_result(f"✅ 语音「{name}」添加成功！\n📁 文件：{name}{ext}\n💾 大小：{len(audio_data) / 1024:.2f} KB")
        except Exception as e:
            logger.error(f"保存语音失败：{e}")
            yield event.plain_result(f"❌ 保存语音失败：{str(e)}")

    @filter.command("voice.delete")
    async def voice_delete(self, event: AstrMessageEvent, name: str):
        """删除语音"""
        if name not in self.voice_list:
            yield event.plain_result(f"❌ 语音「{name}」不存在")
            return

        exts = ['.mp3', '.wav', '.ogg', '.silk', '.amr']
        for ext in exts:
            file_path = os.path.join(self.voices_dir, f"{name}{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                break

        self._scan_voices()
        yield event.plain_result(f"✅ 语音「{name}」已删除")

    @filter.command("voice.reload")
    async def voice_reload(self, event: AstrMessageEvent):
        """重新扫描语音列表"""
        self._scan_voices()
        yield event.plain_result(f"✅ 语音列表已刷新，共 {len(self.voice_list)} 条语音")

    @filter.command("voice.list")
    async def voice_list(self, event: AstrMessageEvent, page: int = 1):
        """查看语音列表"""
        if not self.voice_list:
            yield event.plain_result("📭 暂无可用语音")
            return

        per_page = 10
        total_pages = (len(self.voice_list) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        start = (page - 1) * per_page
        end = start + per_page
        voices = self.voice_list[start:end]

        msg = f"📋 语音列表 (第 {page}/{total_pages} 页)\n" + "\n".join([f"  • {v}" for v in voices])
        yield event.plain_result(msg)
