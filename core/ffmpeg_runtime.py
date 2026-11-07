"""Locate FFmpeg or install a private, prebuilt runtime on demand."""

import asyncio
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

from astrbot.api import logger


PACKAGE = "imageio-ffmpeg==0.8.1"
RUNTIME_DIR = "ffmpeg-runtime-0.8.1"
RETRY_SECONDS = 300
INSTALL_TIMEOUT = 300
MANUAL_GUIDE = (
    "请在运行 AstrBot 的环境中手动安装 FFmpeg 并加入 PATH，"
    "执行 ffmpeg -version 验证；容器部署请在容器或镜像内安装，"
    "安装后重启 AstrBot。详见插件 README 的视频识别说明。"
)


class FFmpegInstallError(RuntimeError):
    pass


_tasks: dict[Path, asyncio.Task[str]] = {}
_failures: dict[Path, tuple[float, str]] = {}


async def _run(*args: str, timeout: int) -> tuple[int, str]:
    with tempfile.TemporaryFile() as output:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=output,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            code = await asyncio.wait_for(process.wait(), timeout=timeout)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        output.seek(0, os.SEEK_END)
        output.seek(max(0, output.tell() - 4096))
        return code, output.read().decode("utf-8", errors="replace")


async def _private_binary(directory: Path) -> str | None:
    binaries = directory / "imageio_ffmpeg" / "binaries"
    candidates = sorted(path for path in binaries.glob("ffmpeg-*") if path.is_file())
    if len(candidates) != 1:
        return None
    try:
        code, _ = await _run(str(candidates[0]), "-version", timeout=10)
    except (OSError, asyncio.TimeoutError):
        return None
    return str(candidates[0]) if code == 0 else None


async def _install(data_dir: Path) -> str:
    runtime = data_dir / RUNTIME_DIR
    found = await _private_binary(runtime)
    if found:
        return found
    if runtime.exists():
        raise FFmpegInstallError(f"已安装的私有 FFmpeg 无法运行，请移除 {runtime} 后重试")

    data_dir.mkdir(parents=True, exist_ok=True)
    logger.info("未找到 FFmpeg，正在为视频识别安装私有 FFmpeg（%s）", PACKAGE)
    with tempfile.TemporaryDirectory(prefix="ffmpeg-install-", dir=data_dir) as temporary:
        target = Path(temporary) / "package"
        try:
            code, output = await _run(
                sys.executable, "-m", "pip", "install", "--no-input",
                "--disable-pip-version-check", "--no-deps", "--only-binary=:all:",
                "--timeout", "15", "--retries", "1", "--target", str(target), PACKAGE,
                timeout=INSTALL_TIMEOUT,
            )
        except asyncio.TimeoutError as exc:
            raise FFmpegInstallError(f"自动安装超时（{INSTALL_TIMEOUT} 秒）") from exc
        except OSError as exc:
            raise FFmpegInstallError(f"无法启动 pip：{exc}") from exc
        if code:
            safe_output = re.sub(r"https?://[^\s]+", "[包源地址]", output).strip()
            raise FFmpegInstallError(f"pip 安装失败（退出码 {code}）：{safe_output or '无错误输出'}")
        if not await _private_binary(target):
            raise FFmpegInstallError("安装包未提供适用于当前系统的可执行 FFmpeg")
        try:
            target.rename(runtime)
        except OSError as exc:
            found = await _private_binary(runtime)
            if found:
                return found
            raise FFmpegInstallError(f"保存私有 FFmpeg 失败：{exc}") from exc
    found = await _private_binary(runtime)
    if not found:
        raise FFmpegInstallError("安装后的 FFmpeg 无法运行")
    logger.info("已安装私有 FFmpeg：%s", found)
    return found


async def ensure_ffmpeg(data_dir: Path) -> str:
    system = shutil.which("ffmpeg")
    if system:
        return system
    data_dir = Path(data_dir).resolve()
    failure = _failures.get(data_dir)
    if failure and time.monotonic() - failure[0] < RETRY_SECONDS:
        raise FFmpegInstallError(failure[1])
    task = _tasks.get(data_dir)
    if task is None:
        task = asyncio.create_task(_install(data_dir))
        _tasks[data_dir] = task

        def finish(completed: asyncio.Task[str]) -> None:
            _tasks.pop(data_dir, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is not None:
                message = f"FFmpeg 自动安装失败：{error}。{MANUAL_GUIDE}"
                _failures[data_dir] = (time.monotonic(), message)
                logger.error("%s", message)
            else:
                _failures.pop(data_dir, None)

        task.add_done_callback(finish)
    try:
        return await asyncio.shield(task)
    except Exception as exc:
        raise FFmpegInstallError(f"FFmpeg 自动安装失败：{exc}。{MANUAL_GUIDE}") from exc
