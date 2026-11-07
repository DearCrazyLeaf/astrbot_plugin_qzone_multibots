"""Optional, bounded video frame analysis through an explicitly selected provider."""

import asyncio
import base64
import ipaddress
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
from astrbot.api import logger
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver

from .ffmpeg_runtime import FFmpegInstallError, ensure_ffmpeg


class VideoAnalysisError(RuntimeError):
    pass


class PublicResolver(AbstractResolver):
    def __init__(self):
        self._resolver = DefaultResolver()

    async def resolve(self, host, port=0, family=socket.AF_INET):
        addresses = await self._resolver.resolve(host, port, family)
        if not addresses or any(
            not ipaddress.ip_address(item["host"]).is_global for item in addresses
        ):
            raise VideoAnalysisError("视频地址解析到非公网地址")
        return addresses

    async def close(self):
        await self._resolver.close()


def validate_video_url(url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not any(host == suffix or host.endswith("." + suffix) for suffix in (
            "qq.com", "gtimg.cn", "qpic.cn"
        ))
    ):
        raise VideoAnalysisError("视频地址不是允许的腾讯 HTTPS 媒体地址")


async def extract_frames(
    url: str, data_dir: Path, settings: dict | None = None
) -> list[str]:
    settings = settings or {}
    max_download_bytes = int(settings.get("max_download_mb", 30)) * 1024 * 1024
    max_duration = int(settings.get("max_duration_seconds", 60))
    frame_interval = int(settings.get("frame_interval_seconds", 10))
    max_frames = int(settings.get("max_frames", 6))
    frame_dimension = int(settings.get("max_frame_dimension", 768))
    validate_video_url(url)
    try:
        ffmpeg = await ensure_ffmpeg(data_dir)
    except FFmpegInstallError as exc:
        raise VideoAnalysisError("FFmpeg 自动安装失败，请查看后台日志并手动安装 FFmpeg") from exc
    with tempfile.TemporaryDirectory(prefix="qzone-video-") as directory:
        root = Path(directory)
        source = root / "input.mp4"
        connector = aiohttp.TCPConnector(resolver=PublicResolver())
        async with aiohttp.ClientSession(
            connector=connector, timeout=aiohttp.ClientTimeout(total=30), trust_env=False
        ) as session:
            async with session.get(url, allow_redirects=False) as response:
                if response.status != 200:
                    raise VideoAnalysisError(f"视频下载失败：HTTP {response.status}")
                if response.content_length and response.content_length > max_download_bytes:
                    raise VideoAnalysisError(f"视频超过 {max_download_bytes // (1024 * 1024)} MiB 限制")
                size = 0
                with source.open("wb") as target:
                    async for chunk in response.content.iter_chunked(65536):
                        size += len(chunk)
                        if size > max_download_bytes:
                            raise VideoAnalysisError(f"视频超过 {max_download_bytes // (1024 * 1024)} MiB 限制")
                        target.write(chunk)
        with source.open("rb") as media:
            header = media.read(12)
        if len(header) < 12 or header[4:8] != b"ftyp":
            raise VideoAnalysisError("仅支持 MP4 格式视频")
        process = await asyncio.create_subprocess_exec(
            ffmpeg, "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-threads", "1", "-i", str(source), "-t", str(max_duration),
            "-vf", f"fps=1/{frame_interval}:round=up:start_time=0,"
                   f"scale={frame_dimension}:{frame_dimension}:force_original_aspect_ratio=decrease",
            "-frames:v", str(max_frames), "-pix_fmt", "yuvj420p", str(root / "frame-%02d.jpg"),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            code = await asyncio.wait_for(process.wait(), timeout=30)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if code:
            raise VideoAnalysisError("FFmpeg 抽帧失败")
        frames = sorted(root.glob("frame-*.jpg"))
        if not frames:
            raise VideoAnalysisError("视频没有可读取的画面")
        return [
            "data:image/jpeg;base64," + base64.b64encode(frame.read_bytes()).decode("ascii")
            for frame in frames
        ]


async def analyze_post(post, config, context) -> None:
    if post.video_analysis:
        return
    if not post.videos:
        if post.has_video:
            post.video_analysis = "接口未提供视频播放地址，无法识别"
        return
    settings = config._data.get("video") or {}
    provider_id = str(settings.get("provider_id") or "").strip()
    if not provider_id:
        post.video_analysis = "未配置视频识别模型，未识别视频内容"
        return
    provider = context.get_provider_by_id(provider_id)
    if provider is None or not callable(getattr(provider, "text_chat", None)):
        post.video_analysis = "视频识别失败：配置的模型不存在或不可用"
        logger.warning("视频识别模型不可用")
        return
    results = []
    max_videos = int(settings.get("max_videos", 3))
    provider_timeout = int(settings.get("provider_timeout_seconds", 60))
    max_duration = int(settings.get("max_duration_seconds", 60))
    for index, url in enumerate(post.videos[:max_videos], 1):
        try:
            frames = await extract_frames(url, config.data_dir, settings)
            response = await asyncio.wait_for(provider.text_chat(
                prompt=f"请简要描述这些按时间顺序抽取的视频画面。仅依据可见内容，不要推断声音或未展示的情节。抽帧范围为视频前 {max_duration} 秒。",
                image_urls=frames,
            ), timeout=provider_timeout)
            summary = str(response.completion_text or "").strip()
            if not summary:
                raise VideoAnalysisError("模型返回空内容")
            results.append(f"视频 {index}（仅基于前 {max_duration} 秒抽帧，不含音频）：{summary}")
        except Exception as exc:
            logger.warning("视频 %s 识别失败：%s", index, type(exc).__name__)
            reason = str(exc) if isinstance(exc, VideoAnalysisError) else type(exc).__name__
            results.append(f"视频 {index} 识别失败：{reason}")
    if len(post.videos) > max_videos:
        results.append("其余视频超过单次识别上限，未识别")
    post.video_analysis = "\n".join(results)
