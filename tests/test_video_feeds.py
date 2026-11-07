import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.db import PostDB
from core.model import Post
from core.qzone.client import QzoneHttpClient
from core.qzone.api import QzoneAPI
from core.qzone.constants import QZONE_INTERNAL_META_KEY, QZONE_INTERNAL_HTTP_STATUS_KEY
from core.qzone.model import ApiResponse, QzoneContext
from core.qzone.parser import QzoneParser
from core.service import PostService
from core.settings_editor import apply_settings, load_schema, settings_values, validate_settings
from core.video_analysis import VideoAnalysisError, analyze_post, extract_frames, validate_video_url


class VideoFeedTests(unittest.TestCase):
    def test_structured_video_and_image_are_separate(self):
        posts = QzoneParser.parse_feeds([{
            "tid": "one",
            "uin": 123456,
            "pic": [
                {"url2": "https://example.test/cover.jpg",
                 "video_info": {"play_url": "https://example.test/play?token=x"}},
                {"url2": "https://example.test/photo.jpg"},
            ],
            "video": [{"url3": "https://example.test/other.mp4"}, {}],
        }])
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].images, ["https://example.test/photo.jpg"])
        self.assertEqual(posts[0].videos, [
            "https://example.test/play?token=x",
            "https://example.test/other.mp4",
        ])

    def test_album_video_is_distinct_and_plain_album_is_excluded(self):
        key = "http://user.qzone.qq.com/123456/photo/album-key/media-key"
        response = {"data": {"data": [
            {"appid": "4", "uin": "123456", "key": "video", "abstime": "1",
             "typeid": "11", "curkey": key, "unikey": key,
             "html": '<div class="f-info">album</div>'
                     '<div class="img-box f-video-wrap play" url3="https://example.test/play">'
                     '<img src="https://example.test/cover.jpg"></div>'},
            {"appid": "4", "uin": "123456", "key": "photo", "abstime": "2",
             "html": '<div class="img-box"><img src="https://example.test/photo.jpg"></div>'},
        ]}}
        posts, _, _ = QzoneParser.parse_recent_feeds(response)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].appid, 4)
        self.assertEqual(posts[0].like_typeid, 11)
        self.assertEqual(posts[0].curkey, key)
        self.assertEqual(posts[0].unikey, key)
        self.assertEqual(posts[0].videos, ["https://example.test/play"])
        self.assertEqual(posts[0].images, [])

    def test_detail_merge_retains_media_from_same_feed(self):
        source = Post(
            tid="one", uin=123456, videos=["https://example.test/v"],
            appid=4, like_typeid=11,
            curkey="http://user.qzone.qq.com/123456/photo/album/photo",
            unikey="http://user.qzone.qq.com/123456/photo/album/photo",
        )
        target = Post(tid="one", uin=123456, images=["https://example.test/i"])
        result = PostService._merge_post_reference(source, target)
        self.assertEqual(result.videos, source.videos)
        self.assertEqual(result.images, target.images)
        self.assertEqual(result.appid, 4)
        self.assertEqual(result.like_typeid, 11)
        self.assertEqual(result.curkey, source.curkey)

    def test_video_marker_without_url_is_not_an_image(self):
        post = QzoneParser.parse_feeds([{
            "tid": "one", "uin": 123456,
            "pic": [{"url2": "https://example.test/cover", "video_info": {}}],
        }])[0]
        self.assertTrue(post.has_video)
        self.assertEqual(post.images, [])
        self.assertEqual(post.videos, [])

    def test_direct_feed_parser_extracts_video_from_qzone_html(self):
        url = "https://video.gtimg.cn/clip.mp4"
        html = f'<div class="img-box f-video-wrap play" url3="{url}"></div>'
        for appid in (311, 4):
            with self.subTest(appid=appid):
                posts = QzoneParser.parse_feeds([{
                    "tid": "feed-id",
                    "uin": 999999,
                    "appid": appid,
                    "typeid": 11 if appid == 4 else 0,
                    "html": html,
                }])

                self.assertEqual(posts[0].videos, [url])
                self.assertTrue(posts[0].has_video)
                self.assertIn(f"[视频]({url})", posts[0].to_str())

    def test_album_like_context_preserves_photo_keys_and_typeid(self):
        key = "http://user.qzone.qq.com/999999/photo/album-key/media-key"
        posts = QzoneParser.parse_feeds([{
            "tid": "feed-id",
            "uin": 999999,
            "appid": 4,
            "typeid": 11,
            "curkey": key,
            "unikey": key,
            "abstime": "1793974906",
        }])

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].like_typeid, 11)
        self.assertEqual(posts[0].curkey, key)
        self.assertEqual(posts[0].unikey, key)
        self.assertEqual(posts[0].like_abstime, 1793974906)

    def test_album_like_context_does_not_invent_photo_keys(self):
        posts = QzoneParser.parse_feeds([{
            "tid": "feed-id",
            "uin": 999999,
            "appid": 4,
        }])

        self.assertEqual(posts[0].like_typeid, 11)
        self.assertEqual(posts[0].curkey, "")
        self.assertEqual(posts[0].unikey, "")


class LikeContextPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_album_like_keys_and_typeid_survive_database_roundtrip(self):
        key = "http://user.qzone.qq.com/999999/photo/album-key/media-key"
        with tempfile.TemporaryDirectory() as directory:
            database = object.__new__(PostDB)
            database.db_path = str(Path(directory) / "qzone.db")
            await database.initialize()
            await database.save(Post(
                tid="feed-id",
                uin=999999,
                appid=4,
                like_typeid=11,
                curkey=key,
                unikey=key,
                like_abstime=1793974906,
            ))

            restored = await database.get("feed-id", key="tid")

        self.assertIsNotNone(restored)
        self.assertEqual(restored.like_typeid, 11)
        self.assertEqual(restored.curkey, key)
        self.assertEqual(restored.unikey, key)
        self.assertEqual(restored.like_abstime, 1793974906)


class DashboardPaginationTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_friend_feed_page_without_has_more_metadata_can_continue(self):
        feeds = [
            {
                "appid": "311",
                "uin": "123456",
                "key": f"feed-{timestamp}",
                "abstime": str(timestamp),
                "html": f'<div class="f-info">post {timestamp}</div>',
            }
            for timestamp in range(100, 94, -1)
        ]
        raw_data = {"data": {"data": feeds}}
        service = object.__new__(PostService)
        service.qzone = SimpleNamespace(
            get_recent_feeds=AsyncMock(return_value=ApiResponse(
                ok=True, code=0, message=None, data=raw_data, raw=raw_data
            )),
            cfg=SimpleNamespace(debug_mode=False),
        )
        service.db = SimpleNamespace(save=AsyncMock())

        posts, has_more, cursor = await service.query_feeds(num=10)

        self.assertEqual(len(posts), 6)
        self.assertTrue(has_more)
        self.assertEqual(cursor, "95")

    async def test_empty_following_page_marks_feed_exhausted(self):
        raw_data = {"data": {"data": []}}
        service = object.__new__(PostService)
        service.qzone = SimpleNamespace(
            get_recent_feeds=AsyncMock(return_value=ApiResponse(
                ok=True, code=0, message=None, data=raw_data, raw=raw_data
            )),
            cfg=SimpleNamespace(debug_mode=False),
        )

        posts, has_more, cursor = await service.query_feeds(cursor="95", num=10)

        self.assertEqual(posts, [])
        self.assertFalse(has_more)
        self.assertEqual(cursor, "")

    async def test_album_video_can_be_liked_and_unliked(self):
        post = Post(tid="album-video", uin=123456, appid=4)
        qzone = SimpleNamespace(like=AsyncMock(return_value=ApiResponse(
            ok=True, code=0, message="succ", data="", raw={}
        )))
        service = PostService(
            qzone,
            SimpleNamespace(get_uin=AsyncMock(return_value=999999)),
            None,
            None,
        )

        result = await service.like_posts(post, unlike=True)

        self.assertEqual(result.status, "accepted_unverified")
        qzone.like.assert_awaited_once_with(post, unlike=True)


class SettingsTests(unittest.TestCase):
    def test_validate_and_update_preserves_cached_group(self):
        schema = load_schema()
        values = settings_values({}, schema)
        values["polling"]["interval"] = 20
        validated = validate_settings(values, schema)
        original_group = {}
        data = {"polling": original_group}
        apply_settings(data, validated)
        self.assertIs(data["polling"], original_group)
        self.assertEqual(original_group["interval"], 20)
        values["polling"]["interval"] = 13
        with self.assertRaises(ValueError):
            validate_settings(values, schema)

    def test_rejects_unknown_fields_and_invalid_qq_numbers(self):
        schema = load_schema()
        values = settings_values({}, schema)
        values["source"]["ignore_users"] = ["not-a-qq-number"]
        with self.assertRaises(ValueError):
            validate_settings(values, schema)
        values["source"]["ignore_users"] = []
        values["extra"] = True
        with self.assertRaises(ValueError):
            validate_settings(values, schema)


class RedirectTests(unittest.IsolatedAsyncioTestCase):
    async def test_like_redirect_never_becomes_success(self):
        response = SimpleNamespace(
            status=302,
            headers={"Location": "https://w.qzone.qq.com/other"},
            text=AsyncMock(return_value=""),
        )

        class Request:
            async def __aenter__(self):
                return response

            async def __aexit__(self, *args):
                return False

        client = object.__new__(QzoneHttpClient)
        client.cfg = SimpleNamespace(debug_mode=False)
        client.session = SimpleNamespace(get_ctx=AsyncMock(
            return_value=QzoneContext(123456, "skey", "p_skey")
        ))
        client._session = SimpleNamespace(request=lambda **kwargs: Request())
        raw = await client.request(
            "POST", "https://w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
        )
        self.assertFalse(ApiResponse.from_raw(raw).ok)
        self.assertIn("重定向", raw["message"])

    async def test_redirect_tries_alternate_endpoint(self):
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(
            return_value=QzoneContext(123456, "skey", "p_skey")
        ))
        api.request = AsyncMock(side_effect=[
            {"code": -1, "message": "重定向",
             QZONE_INTERNAL_META_KEY: {QZONE_INTERNAL_HTTP_STATUS_KEY: 302}},
            {"code": 0, "data": {},
             QZONE_INTERNAL_META_KEY: {QZONE_INTERNAL_HTTP_STATUS_KEY: 200}},
        ])
        result = await api.like(Post(tid="one", uin=999999))
        self.assertTrue(result.ok)
        self.assertEqual(api.request.await_count, 2)

    async def test_unlike_uses_its_endpoint_and_preserves_album_appid(self):
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(
            return_value=QzoneContext(123456, "skey", "p_skey")
        ))
        api.request = AsyncMock(return_value={
            "code": 0, "subcode": 0, "message": "succ", "data": ""
        })
        post = Post(
            tid="feed-id",
            uin=999999,
            appid=4,
            like_typeid=11,
            curkey="https://user.qzone.qq.com/999999/photo/album-key/media-key",
            unikey="https://user.qzone.qq.com/999999/photo/album-key/media-key",
            like_abstime=1793974906,
        )

        response = await api.like(post, unlike=True)

        self.assertTrue(response.ok)
        args = api.request.await_args
        self.assertEqual(args.args[1], api.UNLIKE_URL)
        self.assertEqual(args.kwargs["data"]["appid"], 4)
        self.assertEqual(args.kwargs["data"]["typeid"], 11)
        self.assertEqual(
            args.kwargs["data"]["curkey"],
            "http://user.qzone.qq.com/999999/photo/album-key/media-key",
        )
        self.assertEqual(args.kwargs["data"]["fid"], "feed-id")
        self.assertNotIn("opr_type", args.kwargs["data"])

    async def test_album_like_uses_photo_keys_and_typeid(self):
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(
            return_value=QzoneContext(123456, "skey", "p_skey")
        ))
        api.request = AsyncMock(return_value={
            "code": 0, "subcode": 0, "message": "succ", "data": ""
        })
        post = Post(
            tid="feed-id",
            uin=999999,
            appid=4,
            like_typeid=11,
            curkey="http://user.qzone.qq.com/999999/photo/album-key/media-key",
            unikey="http://user.qzone.qq.com/999999/photo/album-key/media-key",
            like_abstime=1793974906,
        )

        response = await api.like(post)

        self.assertTrue(response.ok)
        args = api.request.await_args
        self.assertEqual(args.args[1], api.DOLIKE_URL)
        self.assertEqual(args.kwargs["data"]["appid"], 4)
        self.assertEqual(args.kwargs["data"]["typeid"], 11)
        self.assertEqual(args.kwargs["data"]["curkey"], post.curkey)
        self.assertEqual(args.kwargs["data"]["unikey"], post.unikey)

    async def test_album_like_requires_qzone_photo_keys(self):
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(
            return_value=QzoneContext(123456, "skey", "p_skey")
        ))
        api.request = AsyncMock()

        with self.assertRaisesRegex(ValueError, "缺少 QQ 返回的 curkey/unikey"):
            await api.like(Post(tid="feed-id", uin=999999, appid=4))
        api.request.assert_not_awaited()

    def test_parse_like_response_html_callback(self):
        raw = QzoneParser.parse_response(
            '<html><body><script>frameElement.callback({'
            '"code":0,"subcode":0,"message":"succ","data":""'
            '});</script></body></html>'
        )

        self.assertEqual(raw["code"], 0)
        self.assertEqual(raw["subcode"], 0)
        self.assertEqual(raw["message"], "succ")

    async def test_like_form_matches_captured_qzone_payload(self):
        context = QzoneContext(123456, "skey", "p_skey")
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(return_value=context))
        api.request = AsyncMock(return_value={
            "code": 0, "subcode": 0, "message": "succ", "data": ""
        })
        post = Post(
            tid="feed-id",
            uin=999999,
            appid=311,
            curkey="https://user.qzone.qq.com/999999/mood/feed-id",
            unikey="https://user.qzone.qq.com/999999/mood/feed-id",
            like_abstime=1793974821,
        )

        response = await api.like(post)

        self.assertTrue(response.ok)
        args = api.request.await_args
        self.assertEqual(args.args[1], api.DOLIKE_URL)
        self.assertEqual(args.kwargs["params"], {"g_tk": context.gtk2})
        self.assertEqual(args.kwargs["headers"]["referer"], "https://user.qzone.qq.com/123456")
        self.assertEqual(
            args.kwargs["data"],
            {
                "g_tk": context.gtk2,
                "qzreferrer": "https://user.qzone.qq.com/123456",
                "opuin": 123456,
                "unikey": "http://user.qzone.qq.com/999999/mood/feed-id",
                "curkey": "http://user.qzone.qq.com/999999/mood/feed-id",
                "from": 1,
                "appid": 311,
                "typeid": 0,
                "abstime": 1793974821,
                "fid": "feed-id",
                "active": 0,
                "fupdate": 1,
            },
        )

    async def test_unlike_form_matches_captured_qzone_payload(self):
        context = QzoneContext(123456, "skey", "p_skey")
        api = object.__new__(QzoneAPI)
        api.session = SimpleNamespace(get_ctx=AsyncMock(return_value=context))
        api.request = AsyncMock(return_value={
            "code": 0, "subcode": 0, "message": "succ", "data": ""
        })
        post = Post(
            tid="feed-id",
            uin=999999,
            appid=311,
            curkey="https://user.qzone.qq.com/999999/mood/feed-id",
            unikey="https://user.qzone.qq.com/999999/mood/feed-id",
            like_abstime=1793974821,
        )

        response = await api.like(post, unlike=True)

        self.assertTrue(response.ok)
        args = api.request.await_args
        self.assertEqual(args.args[1], api.UNLIKE_URL)
        self.assertEqual(
            args.kwargs["data"],
            {
                "g_tk": context.gtk2,
                "qzreferrer": "https://user.qzone.qq.com/123456",
                "opuin": 123456,
                "unikey": "http://user.qzone.qq.com/999999/mood/feed-id",
                "curkey": "http://user.qzone.qq.com/999999/mood/feed-id",
                "from": 1,
                "appid": 311,
                "typeid": 0,
                "abstime": 1793974821,
                "fid": "feed-id",
                "active": 0,
                "fupdate": 1,
            },
        )

    async def test_unverified_like_does_not_change_post_state(self):
        post = Post(tid="one", uin=999999, liked=False)
        service = PostService(
            SimpleNamespace(like=AsyncMock(return_value=ApiResponse(
                ok=True, code=0, message=None, data={}, raw={}
            ))),
            SimpleNamespace(get_uin=AsyncMock(return_value=123456)),
            None, None,
        )
        result = await service.like_posts(post)
        self.assertEqual(result.status, "accepted_unverified")
        self.assertFalse(post.liked)
        self.assertFalse(result.liked)


class VideoAnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_never_extracts_or_calls_provider(self):
        post = Post(tid="one", videos=["https://video.qq.com/play"])
        context = SimpleNamespace(get_provider_by_id=AsyncMock())
        with patch("core.video_analysis.extract_frames", new_callable=AsyncMock) as extract:
            await analyze_post(post, SimpleNamespace(_data={}), context)
        extract.assert_not_called()
        context.get_provider_by_id.assert_not_called()
        self.assertIn("未配置", post.video_analysis)

    async def test_configured_provider_receives_frames_and_failure_is_explicit(self):
        provider = SimpleNamespace(text_chat=AsyncMock(
            return_value=SimpleNamespace(completion_text="一个场景")
        ))
        context = SimpleNamespace(get_provider_by_id=lambda _: provider)
        config = SimpleNamespace(_data={"video": {"provider_id": "vision"}}, data_dir=Path("test-data"))
        post = Post(tid="one", videos=["https://video.qq.com/play"])
        with patch("core.video_analysis.extract_frames", new=AsyncMock(return_value=["frame"])):
            await analyze_post(post, config, context)
        self.assertEqual(provider.text_chat.await_args.kwargs["image_urls"], ["frame"])
        self.assertIn("不含音频", post.video_analysis)
        self.assertIn("一个场景", post.video_analysis)

        failed = Post(tid="two", videos=["https://video.qq.com/play"])
        with patch("core.video_analysis.extract_frames", new=AsyncMock(side_effect=VideoAnalysisError("未找到 FFmpeg"))):
            await analyze_post(failed, config, context)
        self.assertIn("未找到 FFmpeg", failed.video_analysis)
        self.assertEqual(provider.text_chat.await_count, 1)

    def test_media_url_restricts_schemes_hosts_and_credentials(self):
        validate_video_url("https://video.qq.com/play?token=x")
        for url in ("http://video.qq.com/v", "https://qq.com.evil.test/v",
                    "https://user@video.qq.com/v", "https://127.0.0.1/v"):
            with self.subTest(url=url), self.assertRaises(VideoAnalysisError):
                validate_video_url(url)

    @unittest.skipUnless(os.environ.get("QZONE_TEST_FFMPEG"), "FFmpeg test binary unavailable")
    async def test_real_ffmpeg_extracts_frame_from_small_mp4(self):
        executable = os.environ["QZONE_TEST_FFMPEG"]
        with tempfile.TemporaryDirectory() as directory:
            sample = Path(directory) / "sample.mp4"
            subprocess.run(
                [executable, "-v", "error", "-f", "lavfi", "-i",
                 "color=c=blue:s=64x64:d=2:r=2", "-c:v", "mpeg4", str(sample)],
                check=True, timeout=30,
            )
            video_bytes = sample.read_bytes()

        class Content:
            async def iter_chunked(self, size):
                yield video_bytes

        class Response:
            status = 200
            content_length = len(video_bytes)
            content = Content()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class Session:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            def get(self, *args, **kwargs):
                return Response()

        with patch("core.video_analysis.ensure_ffmpeg", new=AsyncMock(return_value=executable)), \
             patch("core.video_analysis.aiohttp.ClientSession", Session):
            frames = await extract_frames("https://video.qq.com/play", Path(directory))
        self.assertTrue(frames)
        self.assertLessEqual(len(frames), 6)
        self.assertTrue(frames[0].startswith("data:image/jpeg;base64,"))


if __name__ == "__main__":
    unittest.main()
