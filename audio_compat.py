"""Audio preparation helpers for reliable AstrBot Record sending."""

from __future__ import annotations

import asyncio
import hashlib
import io
import shutil
import subprocess
import wave
from pathlib import Path


SILK_SAMPLE_RATE = 24000
FALLBACK_WAV_RATE = 24000


def decode_silk_to_wav_bytes(path: Path) -> bytes:
    """Decode Tencent/standard SILK into mono PCM WAV bytes."""

    import pysilk

    source_path = Path(path)
    pcm_buffer = io.BytesIO()
    with source_path.open("rb") as source:
        pysilk.decode(source, pcm_buffer, SILK_SAMPLE_RATE)
    pcm_data = pcm_buffer.getvalue()
    if not pcm_data:
        raise ValueError("SILK decoder returned empty PCM data")

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SILK_SAMPLE_RATE)
        wav_file.writeframes(pcm_data)
    return wav_buffer.getvalue()


def _cache_target(cache_dir: Path, source: Path) -> tuple[Path, str]:
    stat = source.stat()
    path_key = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:12]
    revision_key = hashlib.sha256(
        f"{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8")
    ).hexdigest()[:12]
    return cache_dir / f"{path_key}-{revision_key}.wav", path_key


def _prune_stale_cache(cache_dir: Path, path_key: str, keep: Path) -> None:
    for candidate in cache_dir.glob(f"{path_key}-*.wav"):
        if candidate == keep:
            continue
        try:
            candidate.unlink()
        except OSError:
            pass


def _ffmpeg_convert(source: Path, target: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is unavailable")
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(FALLBACK_WAV_RATE),
            "-c:a",
            "pcm_s16le",
            str(target),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "ffmpeg conversion failed").strip()
        raise RuntimeError(detail[-1000:])


async def _convert_standard_audio(source: Path, target: Path) -> None:
    """Convert common audio formats to WAV using AstrBot first, ffmpeg second."""

    resolver_error: Exception | None = None
    try:
        from astrbot.core.utils.media_utils import MediaResolver

        converted = await MediaResolver(
            str(source),
            media_type="audio",
            default_suffix=source.suffix or ".wav",
        ).to_path(target_format="wav")
        converted_path = Path(converted)
        if not converted_path.is_file():
            raise FileNotFoundError(f"AstrBot media resolver output not found: {converted_path}")
        shutil.copyfile(converted_path, target)
        return
    except Exception as exc:
        resolver_error = exc

    try:
        await asyncio.to_thread(_ffmpeg_convert, source, target)
    except Exception as ffmpeg_error:
        raise RuntimeError(
            f"audio conversion failed via AstrBot MediaResolver ({type(resolver_error).__name__}) "
            f"and ffmpeg ({type(ffmpeg_error).__name__})"
        ) from ffmpeg_error


class AudioSendCompat:
    """Prepare voice files as WAV and cache converted output per source revision."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self._locks: dict[str, asyncio.Lock] = {}

    async def prepare(self, path: str | Path) -> str:
        source = Path(path).resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        if source.suffix.lower() == ".wav":
            return str(source)

        source_key = str(source)
        lock = self._locks.setdefault(source_key, asyncio.Lock())
        async with lock:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            target, path_key = _cache_target(self.cache_dir, source)
            if target.is_file() and target.stat().st_size > 0:
                return str(target)

            temporary = self.cache_dir / f".{target.stem}.tmp.wav"
            try:
                temporary.unlink(missing_ok=True)
                if source.suffix.lower() == ".silk":
                    temporary.write_bytes(decode_silk_to_wav_bytes(source))
                else:
                    await _convert_standard_audio(source, temporary)
                if not temporary.is_file() or temporary.stat().st_size <= 0:
                    raise RuntimeError("audio converter produced no WAV data")
                temporary.replace(target)
            finally:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

            _prune_stale_cache(self.cache_dir, path_key, target)
            return str(target)
