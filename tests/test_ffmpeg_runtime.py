import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core import ffmpeg_runtime
from core.video_analysis import VideoAnalysisError, extract_frames
from ..main import QzonePlugin


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

    async def test_stale_private_runtime_is_removed_but_current_runtime_is_kept(self):
        stale = self.data_dir / "ffmpeg-runtime-0.8.0"
        stale.mkdir()
        (stale / "old-binary").write_bytes(b"old")
        current = self.data_dir / ffmpeg_runtime.RUNTIME_DIR
        current.mkdir()
        (current / "current-binary").write_bytes(b"current")

        with patch.object(ffmpeg_runtime.shutil, "which", return_value="system-ffmpeg"):
            result = await ffmpeg_runtime.ensure_ffmpeg(self.data_dir)

        self.assertEqual(result, "system-ffmpeg")
        self.assertFalse(stale.exists())
        self.assertTrue((current / "current-binary").exists())

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


class PluginStartupFFmpegTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.data_dir = Path(self.temporary.name)

    def create_plugin(self, provider_id="vision"):
        plugin = object.__new__(QzonePlugin)
        plugin.db = SimpleNamespace(initialize=AsyncMock())
        plugin.cfg = SimpleNamespace(
            _data={"video": {"provider_id": provider_id} if provider_id else {}},
            data_dir=self.data_dir,
            trigger=SimpleNamespace(auto_enabled=False),
            polling=SimpleNamespace(enabled=False),
        )
        plugin._ensure_accounts = lambda: None
        return plugin

    @staticmethod
    def main_module():
        import importlib

        return importlib.import_module(QzonePlugin.__module__)

    async def test_configured_video_provider_checks_ffmpeg_at_plugin_startup(self):
        plugin = self.create_plugin()
        module = self.main_module()
        with patch.object(
            module,
            "ensure_ffmpeg",
            new=AsyncMock(return_value="private-ffmpeg"),
        ) as ensure:
            await plugin.initialize()

        ensure.assert_awaited_once_with(self.data_dir)

    async def test_startup_ffmpeg_failure_propagates_manual_install_guide(self):
        plugin = self.create_plugin()
        module = self.main_module()
        failure = ffmpeg_runtime.FFmpegInstallError(
            "FFmpeg 自动安装失败。请在运行 AstrBot 的环境中手动安装 FFmpeg。"
        )
        with patch.object(
            module,
            "ensure_ffmpeg",
            new=AsyncMock(side_effect=failure),
        ) as ensure:
            with self.assertRaisesRegex(
                ffmpeg_runtime.FFmpegInstallError, "手动安装 FFmpeg"
            ):
                await plugin.initialize()

        ensure.assert_awaited_once_with(self.data_dir)

    async def test_unconfigured_video_provider_skips_startup_install(self):
        plugin = self.create_plugin(provider_id="")
        module = self.main_module()
        with (
            patch.object(module, "ensure_ffmpeg", new=AsyncMock()) as ensure,
            patch.object(module, "cleanup_stale_ffmpeg_runtimes") as cleanup,
        ):
            await plugin.initialize()

        ensure.assert_not_awaited()
        cleanup.assert_called_once_with(self.data_dir)
