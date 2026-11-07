import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from core import ffmpeg_runtime
from core.video_analysis import VideoAnalysisError, extract_frames


class FFmpegRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ffmpeg_runtime._tasks.clear()
        ffmpeg_runtime._failures.clear()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data_dir = Path(self.temporary.name)

    async def test_system_ffmpeg_bypasses_install(self):
        with patch.object(ffmpeg_runtime.shutil, "which", return_value="system-ffmpeg"), \
             patch.object(ffmpeg_runtime, "_install", new_callable=AsyncMock) as install:
            self.assertEqual(await ffmpeg_runtime.ensure_ffmpeg(self.data_dir), "system-ffmpeg")
            install.assert_not_called()

    async def test_concurrent_requests_share_install(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def install(_):
            started.set()
            await release.wait()
            return "private-ffmpeg"

        with patch.object(ffmpeg_runtime.shutil, "which", return_value=None), \
             patch.object(ffmpeg_runtime, "_install", side_effect=install) as installer:
            first = asyncio.create_task(ffmpeg_runtime.ensure_ffmpeg(self.data_dir))
            await started.wait()
            second = asyncio.create_task(ffmpeg_runtime.ensure_ffmpeg(self.data_dir))
            await asyncio.sleep(0)
            release.set()
            self.assertEqual(await asyncio.gather(first, second), ["private-ffmpeg"] * 2)
            installer.assert_called_once()

    async def test_failure_logs_guidance_throttles_and_system_install_recovers(self):
        with patch.object(ffmpeg_runtime.shutil, "which", return_value=None) as which, \
             patch.object(ffmpeg_runtime, "_install", new=AsyncMock(side_effect=OSError("network down"))) as install, \
             patch.object(ffmpeg_runtime.logger, "error") as log:
            for _ in range(2):
                with self.assertRaisesRegex(ffmpeg_runtime.FFmpegInstallError, "手动安装 FFmpeg"):
                    await ffmpeg_runtime.ensure_ffmpeg(self.data_dir)
            install.assert_awaited_once()
            self.assertIn("network down", log.call_args.args[1])
            self.assertIn("ffmpeg -version", log.call_args.args[1])
            which.return_value = "system-ffmpeg"
            self.assertEqual(await ffmpeg_runtime.ensure_ffmpeg(self.data_dir), "system-ffmpeg")

    async def test_pip_failure_is_diagnostic_and_does_not_publish_partial_package(self):
        with patch.object(ffmpeg_runtime, "_run", new=AsyncMock(
            return_value=(1, "ERROR: failed https://user:password@example.test/simple")
        )):
            with self.assertRaises(ffmpeg_runtime.FFmpegInstallError) as error:
                await ffmpeg_runtime._install(self.data_dir)
        self.assertIn("退出码 1", str(error.exception))
        self.assertNotIn("password", str(error.exception))
        self.assertFalse((self.data_dir / ffmpeg_runtime.RUNTIME_DIR).exists())
        self.assertEqual(list(self.data_dir.iterdir()), [])

    async def test_successful_install_is_private_and_reused(self):
        async def run(*args, timeout):
            if "-m" in args:
                target = Path(args[args.index("--target") + 1])
                binary = target / "imageio_ffmpeg" / "binaries" / "ffmpeg-test"
                binary.parent.mkdir(parents=True)
                binary.write_bytes(b"test")
            return 0, ""

        with patch.object(ffmpeg_runtime.shutil, "which", return_value=None), \
             patch.object(ffmpeg_runtime, "_run", side_effect=run) as runner:
            first = await ffmpeg_runtime.ensure_ffmpeg(self.data_dir)
            second = await ffmpeg_runtime.ensure_ffmpeg(self.data_dir)
        self.assertEqual(first, second)
        self.assertTrue(Path(first).is_relative_to(self.data_dir.resolve() / ffmpeg_runtime.RUNTIME_DIR))
        installs = [call for call in runner.call_args_list if "-m" in call.args]
        self.assertEqual(len(installs), 1)

    async def test_cancelled_waiter_does_not_cancel_shared_install(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def install(_):
            started.set()
            await release.wait()
            return "private-ffmpeg"

        with patch.object(ffmpeg_runtime.shutil, "which", return_value=None), \
             patch.object(ffmpeg_runtime, "_install", side_effect=install) as installer:
            first = asyncio.create_task(ffmpeg_runtime.ensure_ffmpeg(self.data_dir))
            await started.wait()
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(ffmpeg_runtime.ensure_ffmpeg(self.data_dir))
            release.set()
            self.assertEqual(await second, "private-ffmpeg")
            installer.assert_called_once()

    async def test_extraction_reports_install_failure_without_downloading_video(self):
        with patch("core.video_analysis.ensure_ffmpeg", new=AsyncMock(
            side_effect=ffmpeg_runtime.FFmpegInstallError("failure")
        )), patch("core.video_analysis.aiohttp.ClientSession") as session:
            with self.assertRaisesRegex(VideoAnalysisError, "手动安装 FFmpeg"):
                await extract_frames("https://video.qq.com/play", self.data_dir)
            session.assert_not_called()
