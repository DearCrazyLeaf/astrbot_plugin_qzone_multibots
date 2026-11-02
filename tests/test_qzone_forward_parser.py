import unittest

from core.qzone.parser import QzoneParser


class QzoneForwardParserTests(unittest.TestCase):
    def test_parse_feeds_extracts_nested_share_card_metadata(self):
        posts = QzoneParser.parse_feeds(
            [
                {
                    "tid": "feed-1",
                    "uin": 123456,
                    "name": "好友",
                    "content": "转发动态",
                    "rt_con": {
                        "content": "一起听这首歌",
                        "share_info": {
                            "sourceName": "网易云音乐",
                            "songName": "歌曲标题",
                            "singerName": "歌手",
                            "shareUrl": "https://music.163.com/song?id=1",
                        },
                    },
                }
            ]
        )

        self.assertEqual(len(posts), 1)
        self.assertIn("一起听这首歌", posts[0].rt_con)
        self.assertIn("网易云音乐", posts[0].rt_con)
        self.assertIn("歌曲标题", posts[0].rt_con)
        self.assertIn("歌手", posts[0].rt_con)
        self.assertIn("https://music.163.com/song?id=1", posts[0].rt_con)

    def test_parse_feeds_accepts_string_repost_content(self):
        posts = QzoneParser.parse_feeds(
            [
                {
                    "tid": "feed-2",
                    "uin": 123456,
                    "name": "好友",
                    "rt_con": "普通转发内容",
                }
            ]
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].rt_con, "普通转发内容")

    def test_recent_feed_extracts_card_title_and_external_links(self):
        html = """
        <li>
          <div class="f-info">转发动态</div>
          <div class="txt-box"><a class="nickname">好友</a>：分享给你</div>
          <div class="share-card">
            <p class="txt-box-title ellipsis-one">
              <a href="https://www.bilibili.com/video/BV123">B站视频标题</a>
            </p>
            <p class="txt-box-desc">视频简介</p>
          </div>
        </li>
        """
        response = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "uin": "123456",
                        "key": "feed-3",
                        "abstime": "1710000000",
                        "html": html,
                    }
                ]
            }
        }

        posts, _, _ = QzoneParser.parse_recent_feeds(response)

        self.assertEqual(len(posts), 1)
        self.assertIn("分享给你", posts[0].rt_con)
        self.assertIn("B站视频标题", posts[0].rt_con)
        self.assertIn("视频简介", posts[0].rt_con)
        self.assertIn("https://www.bilibili.com/video/BV123", posts[0].rt_con)

    def test_recent_feed_keeps_links_from_common_share_platforms(self):
        html = """
        <div class="txt-box">
          <a href="https://y.qq.com/n/ryqq/song/1">QQ音乐歌曲</a>
          <a href="https://music.163.com/song?id=2">网易云歌曲</a>
          <a href="https://www.bilibili.com/video/BV123">B站视频</a>
          <a href="https://v.douyin.com/abc/">抖音视频</a>
        </div>
        """
        response = {
            "data": {
                "data": [
                    {
                        "appid": "311",
                        "uin": "123456",
                        "key": "feed-4",
                        "abstime": "1710000000",
                        "html": html,
                    }
                ]
            }
        }

        posts, _, _ = QzoneParser.parse_recent_feeds(response)

        self.assertEqual(len(posts), 1)
        for url in (
            "https://y.qq.com/n/ryqq/song/1",
            "https://music.163.com/song?id=2",
            "https://www.bilibili.com/video/BV123",
            "https://v.douyin.com/abc/",
        ):
            with self.subTest(url=url):
                self.assertIn(url, posts[0].rt_con)


if __name__ == "__main__":
    unittest.main()
