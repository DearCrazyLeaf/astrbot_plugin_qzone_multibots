import unittest

from ..core.model import Post
from ..core.qzone.parser import QzoneParser
from ..main import QzonePlugin


class DashboardPayloadTests(unittest.TestCase):
    def test_duplicate_caption_in_text_and_repost_is_rendered_once(self):
        plugin = object.__new__(QzonePlugin)
        plugin._page_post_refs = {}
        post = Post(tid="video", uin=12345, text="视频配文", rt_con="视频配文", has_video=True)

        payload = plugin._page_post_payload(post)

        self.assertEqual(payload["content"], "视频配文")

    def test_distinct_repost_text_is_preserved(self):
        plugin = object.__new__(QzonePlugin)
        plugin._page_post_refs = {}
        post = Post(tid="repost", uin=12345, text="转发说明", rt_con="原动态内容")

        payload = plugin._page_post_payload(post)

        self.assertEqual(payload["content"], "转发说明\n原动态内容")

    def test_detail_media_is_not_duplicated_across_image_and_video_fields(self):
        source = Post(
            tid="video",
            uin=12345,
            images=[
                "https://example.test/clip.mp4?token=old",
                "https://example.test/photo.jpg?size=small",
                "https://example.test/photo.jpg?size=large",
            ],
            videos=["https://example.test/clip.mp4?token=new"],
            appid=4,
            like_typeid=11,
            curkey="http://user.qzone.qq.com/12345/photo/album-key/media-key",
            unikey="http://user.qzone.qq.com/12345/photo/album-key/media-key",
        )
        target = Post(
            tid="video",
            uin=12345,
            images=["https://example.test/clip.mp4?token=new"],
            videos=["https://example.test/clip.mp4?token=new"],
        )

        result = QzonePlugin._preserve_like_reference(source, target)

        self.assertEqual(
            result.images, ["https://example.test/photo.jpg?size=small"]
        )
        self.assertEqual(
            result.videos, ["https://example.test/clip.mp4?token=new"]
        )
        self.assertEqual(result.appid, 4)
        self.assertEqual(result.like_typeid, 11)
        self.assertEqual(result.curkey, source.curkey)

    def test_album_video_payload_allows_like_and_comment(self):
        plugin = object.__new__(QzonePlugin)
        plugin._page_post_refs = {}
        key = "http://user.qzone.qq.com/12345/photo/album-key/media-key"
        post = Post(
            tid="album-video",
            uin=12345,
            appid=4,
            like_typeid=11,
            curkey=key,
            unikey=key,
            videos=["https://video.test/play"],
        )

        payload = plugin._page_post_payload(post)

        self.assertTrue(payload["can_like"])
        self.assertTrue(payload["can_comment"])
        self.assertFalse(payload["read_only"])

    def test_album_video_without_qzone_photo_keys_is_not_likeable(self):
        plugin = object.__new__(QzonePlugin)
        plugin._page_post_refs = {}
        post = Post(tid="album-video", uin=12345, appid=4, videos=["https://video.test/play"])

        payload = plugin._page_post_payload(post)

        self.assertFalse(payload["can_like"])
        self.assertTrue(payload["can_comment"])
        self.assertFalse(payload["read_only"])

    def test_video_like_keys_from_nested_context_enable_dashboard_action(self):
        plugin = object.__new__(QzonePlugin)
        plugin._page_post_refs = {}
        key = "http://user.qzone.qq.com/12345/photo/album-key/media-key"
        post = QzoneParser.parse_feeds([{
            "tid": "album-video",
            "uin": 12345,
            "appid": 4,
            "like": {"typeid": 11, "curkey": key, "unikey": key},
            "html": '<div class="img-box f-video-wrap play" url3="https://video.test/play"></div>',
        }])[0]

        payload = plugin._page_post_payload(post)

        self.assertTrue(post.videos)
        self.assertEqual(post.like_typeid, 11)
        self.assertTrue(payload["can_like"])


if __name__ == "__main__":
    unittest.main()
