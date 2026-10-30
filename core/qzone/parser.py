# parser.py
import json
import re
from typing import Any

import bs4
import json5
from astrbot.api import logger

from ..model import Comment, Post
from .constants import (
    QZONE_CODE_UNKNOWN,
    QZONE_MSG_EMPTY_RESPONSE,
    QZONE_MSG_INVALID_RESPONSE,
    QZONE_MSG_JSON_PARSE_ERROR,
    QZONE_MSG_NON_OBJECT_RESPONSE,
)


class QzoneParser:
    """QQ 空间响应解析器"""

    @staticmethod
    def compute_unikey(appid: int, hostuin: int, fid: str) -> str:
        """Ultra 兼容: 根据 appid/hostuin/fid 构造默认 unikey/curkey。"""
        if appid == 311:
            return f"https://user.qzone.qq.com/{hostuin}/mood/{fid}"
        return f"https://user.qzone.qq.com/{hostuin}/app/{appid}/{fid}"

    @staticmethod
    def normalize_timestamp(value: Any) -> int:
        try:
            timestamp = int(float(value))
        except (TypeError, ValueError, OverflowError):
            return 0
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return timestamp if timestamp > 0 else 0

    @staticmethod
    def _as_optional_bool(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
        return None

    @staticmethod
    def _like_context(raw: dict[str, Any], uin: Any, tid: Any) -> dict[str, Any]:
        nested = [raw]
        for key in ("common", "comm", "cell_comm", "cellComm", "data"):
            value = raw.get(key)
            if isinstance(value, dict):
                nested.append(value)

        def find(*keys: str) -> Any:
            for source in nested:
                for key in keys:
                    value = source.get(key)
                    if value not in (None, ""):
                        return value
            return None

        try:
            appid = int(find("appid", "appId") or 311)
        except (TypeError, ValueError):
            appid = 311
        hostuin = str(uin or "").strip()
        feed_id = str(tid or "").strip()
        fallback_key = ""
        if hostuin and feed_id:
            if appid == 311:
                fallback_key = f"https://user.qzone.qq.com/{hostuin}/mood/{feed_id}"
            else:
                fallback_key = f"https://user.qzone.qq.com/{hostuin}/app/{appid}/{feed_id}"

        like_data = next(
            (
                source.get("like")
                for source in nested
                if isinstance(source.get("like"), dict)
            ),
            {},
        )
        liked_value = None
        for key in ("isliked", "ismylike", "isLike", "islike", "liked"):
            if key in like_data:
                liked_value = QzoneParser._as_optional_bool(like_data[key])
                break
            for source in nested:
                if key in source:
                    liked_value = QzoneParser._as_optional_bool(source[key])
                    break
            if liked_value is not None:
                break

        like_count = 0
        for source in (like_data, *nested):
            for key in ("num", "likeNum", "count", "likenum", "like_num"):
                try:
                    like_count = int(source.get(key) or 0)
                except (TypeError, ValueError):
                    like_count = 0
                if like_count:
                    break
            if like_count:
                break

        abstime = QzoneParser.normalize_timestamp(
            find("abstime", "created_time", "created_at", "create_time", "pubtime")
        )
        return {
            "appid": appid,
            "curkey": str(find("curkey", "curlikekey") or fallback_key),
            "unikey": str(find("unikey", "unlikekey") or fallback_key),
            "like_abstime": abstime,
            "liked": liked_value,
            "like_count": like_count,
        }

    @staticmethod
    def _error_payload(message: str) -> dict[str, Any]:
        return {"code": QZONE_CODE_UNKNOWN, "message": message, "data": {}}

    @staticmethod
    def parse_response(text: str, *, debug: bool = False) -> dict[str, Any]:
        """
        解析 JSON / JSONP / 非标准 JSON
        """

        if debug:
            logger.debug(f"响应数据: {text}")

        if not text or not text.strip():
            logger.warning("响应内容为空")
            return QzoneParser._error_payload(QZONE_MSG_EMPTY_RESPONSE)

        if m := re.search(
            r"callback\s*\(\s*([^{]*(\{.*\})[^)]*)\s*\)",
            text,
            re.I | re.S,
        ):
            json_str = m.group(2)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1 or end < start:
                logger.warning("响应内容缺少 JSON 片段")
                return QzoneParser._error_payload(QZONE_MSG_INVALID_RESPONSE)
            json_str = text[start : end + 1]

        json_str = json_str.replace("undefined", "null").strip()

        try:
            data = json5.loads(json_str)
        except (ValueError, json.JSONDecodeError) as e:
            logger.error(f"JSON 解析错误: {e}")
            return QzoneParser._error_payload(QZONE_MSG_JSON_PARSE_ERROR)

        if not isinstance(data, dict):
            logger.error("JSON 解析结果不是 dict")
            return QzoneParser._error_payload(QZONE_MSG_NON_OBJECT_RESPONSE)

        if debug:
            logger.debug(f"解析后数据: {data}")

        return data

    @staticmethod
    def parse_upload_result(payload: dict[str, Any]) -> tuple[str, str]:
        data = payload["data"]
        picbo = data["url"].split("&bo=", 1)[1]

        richval = ",{},{},{},{},{},{},,{},{}".format(
            data["albumid"],
            data["lloc"],
            data["sloc"],
            data["type"],
            data["height"],
            data["width"],
            data["height"],
            data["width"],
        )
        return picbo, richval


    @staticmethod
    def parse_feeds(msglist: list[dict], *, debug: bool = False) -> list[Post]:
        """解析说说列表"""
        try:
            posts = []
            for msg in msglist:
                if debug:
                    logger.debug(msg)
                # 提取图片信息
                image_urls = []
                for img_data in msg.get("pic", []):
                    for key in ("url2", "url3", "url1", "smallurl"):
                        if raw := img_data.get(key):
                            image_urls.append(raw)
                            break
                # 读取视频封面（按图片处理）
                for video in msg.get("video") or []:
                    video_image_url = video.get("url1") or video.get("pic_url")
                    image_urls.append(video_image_url)
                # 提取视频播放地址
                video_urls = []
                for video in msg.get("video") or []:
                    url = video.get("url3")
                    if url:
                        video_urls.append(url)
                # 提取转发内容
                rt_con = msg.get("rt_con", {}).get("content", "")
                # 提取评论
                comments = Comment.build_list(msg.get("commentlist") or [])
                like_context = QzoneParser._like_context(
                    msg, msg.get("uin", 0), msg.get("tid", 0)
                )
                # 构造Post对象
                post = Post(
                    tid=msg.get("tid", 0),
                    uin=msg.get("uin", 0),
                    name=msg.get("name", ""),
                    avatar_url=msg.get("portrait"),
                    gin=0,
                    text=msg.get("content", "").strip(),
                    images=image_urls,
                    videos=video_urls,
                    anon=False,
                    status="approved",
                    create_time=msg.get("created_time", 0),
                    rt_con=rt_con,
                    comments=comments,
                    extra_text=msg.get("source_name"),
                    **like_context,
                )
                posts.append(post)

            return posts

        except Exception as e:
            logger.error(f"解析说说列表失败: {e}")
            return []

    @staticmethod
    def parse_recent_feeds(data: dict) -> list[Post]:
        """解析最近说说列表"""
        feeds: list = data.get("data", {}).get("data", {})
        if not data:
            return []
        try:
            posts = []
            for feed in feeds:
                if not feed:
                    continue
                # 过滤广告类内容（appid=311）
                appid = str(feed.get("appid", ""))
                if appid != "311":
                    continue
                uin = feed.get("uin", "")
                tid = feed.get("key", "")
                if not uin or not tid:
                    logger.error(f"无效的说说数据: target_qq={uin}, tid={tid}")
                    continue
                create_time = feed.get("abstime", "")
                nickname = feed.get("nickname", "")
                html_content = feed.get("html", "")
                if not html_content:
                    logger.error(f"说说内容为空: UIN={uin}, TID={tid}")
                    continue

                soup = bs4.BeautifulSoup(html_content, "html.parser")

                # 提取文字内容
                text_div = soup.find("div", class_="f-info")
                text = text_div.get_text(strip=True) if text_div else ""
                # 提取转发内容
                rt_con = ""
                txt_box = soup.select_one("div.txt-box")
                if txt_box:
                    # 获取除昵称外的纯文本内容
                    rt_con = txt_box.get_text(strip=True)
                    # 分割掉昵称部分（从第一个冒号开始取内容）
                    if "：" in rt_con:
                        rt_con = rt_con.split("：", 1)[1].strip()
                # 提取图片URL
                image_urls = []
                # 查找所有图片容器
                if img_box := soup.find("div", class_="img-box"):
                    for img in img_box.find_all("img"):  # type: ignore
                        src = img.get("src")  # type: ignore
                        if src and not str(src).startswith(
                            "http://qzonestyle.gtimg.cn"
                        ):  # 过滤表情图标
                            image_urls.append(src)
                # TODO 临时视频处理办法（视频缩略图）
                img_tag = soup.select_one("div.video-img img")
                if img_tag and "src" in img_tag.attrs:
                    image_urls.append(img_tag["src"])
                # 获取视频url
                videos = []
                video_div = soup.select_one("div.img-box.f-video-wrap.play")
                if video_div and "url3" in video_div.attrs:
                    videos.append(video_div["url3"])
                # 获取评论内容
                comments: list[Comment] = []
                # 查找所有评论项（包括主评论和回复）
                comment_items = soup.select("li.comments-item.bor3")
                if comment_items:
                    for item in comment_items:
                        # 提取基本信息
                        data_uin = str(item.get("data-uin", ""))
                        comment_tid = str(item.get("data-tid", ""))
                        nickname = str(item.get("data-nick", ""))

                        # 查找评论内容
                        content_div = item.select_one("div.comments-content")
                        if content_div:
                            # 移除操作按钮（回复/删除）
                            for op in content_div.select("div.comments-op"):
                                op.decompose()
                            # 获取纯文本内容
                            content = content_div.get_text(" ", strip=True).split(
                                ":", 1
                            )[-1]
                        else:
                            content = ""

                        # 提取评论时间（直接使用相对时间字符串）
                        comment_time_span = item.select_one("span.state")
                        comment_time = (
                            comment_time_span.get_text(strip=True)
                            if comment_time_span
                            else ""
                        )

                        # 检查是否是回复
                        parent_tid = None
                        parent_div = item.find_parent("div", class_="mod-comments-sub")
                        if parent_div:
                            parent_li = parent_div.find_parent(
                                "li", class_="comments-item"
                            )
                            if parent_li:
                                parent_tid = str(parent_li.get("data-tid"))  # type: ignore

                        comments.append(
                            Comment(
                                uin=int(data_uin) if data_uin.isdigit() else 0,
                                nickname=nickname,
                                content=content,
                                create_time=0,
                                create_time_str=comment_time,
                                tid=int(comment_tid) if comment_tid.isdigit() else 0,
                                parent_tid=int(parent_tid)
                                if parent_tid and parent_tid.isdigit()
                                else None,
                            )
                        )
                                # 构造Post对象
                like_context = QzoneParser._like_context(feed, uin, tid)

                # 从 HTML 中辅助提取点赞数与点赞状态（若 JSON 字典中未取到）
                if not like_context.get("like_count") or like_context.get("liked") is None:
                    like_elem = soup.select_one("a.f-like, a.item-like, span.f-like-cnt, span.like-num, .qz-like-num")
                    if like_elem:
                        if like_context.get("liked") is None:
                            classes = " ".join(like_elem.get("class", []))
                            if "liked" in classes or "on" in classes or "is-liked" in classes:
                                like_context["liked"] = True
                        if not like_context.get("like_count"):
                            if num_match := re.search(r"\d+", like_elem.get_text()):
                                like_context["like_count"] = int(num_match.group())

                post = Post(
                    tid=str(tid),
                    uin=int(uin),
                    name=str(nickname),
                    avatar_url=feed.get("pic"),
                    text=text,
                    images=list(set(image_urls)),
                    videos=videos,
                    create_time=create_time,
                    rt_con=rt_con,
                    comments=comments,
                    **like_context,
                )
                posts.append(post)

            logger.info(f"成功解析 {len(posts)} 条最新说说")
            return posts
        except Exception as e:
            logger.error(f"解析说说错误：{e}")
            return []
