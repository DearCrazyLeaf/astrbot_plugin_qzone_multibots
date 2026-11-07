# parser.py
import json
import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

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
from .media import extract_feed_media


class QzoneParser:
    """QQ 空间响应解析器"""

    _REPOST_TEXT_FIELDS = {
        "album": "专辑",
        "artist": "歌手/作者",
        "author": "作者",
        "content": "内容",
        "desc": "简介",
        "description": "简介",
        "artist_name": "歌手/作者",
        "artistname": "歌手/作者",
        "jump_url": "链接",
        "link": "链接",
        "music_name": "歌曲",
        "music_title": "标题",
        "name": "名称",
        "nickname": "作者",
        "platform": "平台",
        "singer": "歌手",
        "singer_name": "歌手",
        "singername": "歌手",
        "song_name": "歌曲",
        "song_title": "标题",
        "songname": "歌曲",
        "source_name": "平台",
        "share_url": "链接",
        "share_title": "标题",
        "source": "平台",
        "source_url": "链接",
        "summary": "简介",
        "text": "配文",
        "track_name": "歌曲",
        "trackname": "歌曲",
        "title": "标题",
        "url": "链接",
        "video_title": "标题",
        "video_url": "链接",
        "web_url": "链接",
    }

    @staticmethod
    def compute_unikey(appid: int, hostuin: int, fid: str) -> str:
        """Construct a fallback key only when Qzone's key can be derived."""
        if appid == 311:
            return f"https://user.qzone.qq.com/{hostuin}/mood/{fid}"
        if appid == 4:
            return ""
        return f"https://user.qzone.qq.com/{hostuin}/app/{appid}/{fid}"

    @staticmethod
    def _clean_repost_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        text = value.strip()
        if not text:
            return ""
        if re.search(r"</?[a-z][^>]*>", text, re.I):
            text = bs4.BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
        else:
            text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def extract_repost_text(value: Any) -> str:
        """Extract readable text from nested repost and third-party card data."""
        parts: list[str] = []
        seen: set[str] = set()

        def add(text: str, label: str = "") -> None:
            text = QzoneParser._clean_repost_text(text)
            if not text or text.casefold() in seen:
                return
            seen.add(text.casefold())
            parts.append(f"{label}：{text}" if label else text)

        def visit(item: Any) -> None:
            if isinstance(item, str):
                raw = item.strip()
                if raw.startswith(("{", "[")) and raw.endswith(("}", "]")):
                    try:
                        parsed = json5.loads(raw)
                    except (TypeError, ValueError):
                        parsed = None
                    if isinstance(parsed, (dict, list)):
                        visit(parsed)
                        return
                add(raw)
                return

            if isinstance(item, dict):
                for key, child in item.items():
                    normalized_key = re.sub(
                        r"(?<!^)(?=[A-Z])", "_", str(key).strip()
                    ).lower()
                    label = QzoneParser._REPOST_TEXT_FIELDS.get(normalized_key)
                    if isinstance(child, (dict, list)):
                        visit(child)
                    elif label and isinstance(child, str):
                        add(child, label)
                return

            if isinstance(item, list):
                for child in item:
                    visit(child)

        visit(value)
        return "\n".join(parts)

    @staticmethod
    def _is_external_repost_url(url: str) -> bool:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            return False
        if host == "qq.com" or host.endswith(".qq.com"):
            return any(
                host == domain or host.endswith(f".{domain}")
                for domain in ("y.qq.com", "music.qq.com", "v.qq.com")
            )
        return not host.endswith(
            (".gtimg.cn", ".qpic.cn", ".qlogo.cn", ".qzonestyle.gtimg.cn")
        )

    @staticmethod
    def extract_repost_html(soup: bs4.BeautifulSoup) -> str:
        parts: list[str] = []
        seen: set[str] = set()

        def add(text: str) -> None:
            text = QzoneParser._clean_repost_text(text)
            if text and text.casefold() not in seen:
                seen.add(text.casefold())
                parts.append(text)

        txt_box = soup.select_one("div.txt-box")
        if txt_box:
            text = txt_box.get_text(" ", strip=True)
            if "：" in text:
                text = text.split("：", 1)[1].strip()
            add(text)

        card_selectors = (
            "[class*='txt-box-title']",
            "[class*='txt-box-desc']",
            "[class*='txt-box-summary']",
            "[class*='share-title']",
            "[class*='share-desc']",
            "[class*='card-title']",
            "[class*='video-title']",
            "[class*='music-title']",
        )
        card_nodes = soup.select(", ".join(card_selectors))
        for node in card_nodes:
            add(node.get_text(" ", strip=True) or node.get("title", ""))

        link_nodes = list(txt_box.select("a[href]")) if txt_box else []
        for node in card_nodes:
            if node.name == "a" and node.get("href"):
                link_nodes.append(node)
            link_nodes.extend(node.select("a[href]"))

        for link in link_nodes:
            href = str(link.get("href") or "").strip()
            if not QzoneParser._is_external_repost_url(href):
                continue
            label = link.get_text(" ", strip=True)
            add(f"{label} ({href})" if label else href)

        return "\n".join(parts)

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
        for source in tuple(nested):
            value = source.get("like")
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
        raw_typeid = find("typeid", "typeId")
        try:
            like_typeid = int(
                raw_typeid if raw_typeid is not None else (11 if appid == 4 else 0)
            )
        except (TypeError, ValueError):
            like_typeid = 11 if appid == 4 else 0
        hostuin = str(uin or "").strip()
        feed_id = str(tid or "").strip()
        fallback_key = ""
        if hostuin and feed_id:
            if appid == 311:
                fallback_key = f"https://user.qzone.qq.com/{hostuin}/mood/{feed_id}"

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
            "like_typeid": like_typeid,
            "curkey": str(find("curkey", "curlikekey") or fallback_key),
            "unikey": str(find("unikey", "unlikekey") or fallback_key),
            "like_abstime": abstime,
            "liked": liked_value,
            "like_count": like_count,
        }

    @staticmethod
    def _apply_html_like_context(
        soup: bs4.BeautifulSoup, like_context: dict[str, Any]
    ) -> None:
        nodes = soup.select(
            ".qz_like_btn_v3, [data-curkey], [data-unikey], "
            "[data-isliked], [data-liked], [aria-pressed]"
        )
        for node in nodes:
            for field, aliases in {
                "curkey": ("data-curkey", "curkey", "data-curlikekey"),
                "unikey": ("data-unikey", "unikey", "data-unlikekey"),
            }.items():
                value = next(
                    (
                        node.get(alias)
                        for alias in aliases
                        if node.get(alias) not in (None, "")
                    ),
                    None,
                )
                if value:
                    like_context[field] = unescape(str(value))

            if like_context.get("liked") is None:
                for attr in (
                    "data-isliked",
                    "data-liked",
                    "data-is-like",
                    "aria-pressed",
                ):
                    if attr in node.attrs:
                        liked = QzoneParser._as_optional_bool(node.get(attr))
                        if liked is not None:
                            like_context["liked"] = liked
                            break

            if like_context.get("liked") is None:
                classes = {
                    str(value).casefold() for value in node.get("class", [])
                }
                if any(
                    value in {"liked", "is-liked", "isliked", "qz_like_btn_v3_on"}
                    or value.endswith("_liked")
                    for value in classes
                ):
                    like_context["liked"] = True
                else:
                    action_text = " ".join(
                        str(node.get(attr) or "")
                        for attr in ("title", "aria-label")
                    )
                    action_text = f"{action_text} {node.get_text(' ', strip=True)}"
                    if any(
                        marker in action_text
                        for marker in ("取消点赞", "取消赞", "已点赞", "已赞")
                    ):
                        like_context["liked"] = True
                    elif re.fullmatch(
                        r"\s*(?:赞|点赞|赞一下|喜欢)\s*\d*\s*",
                        action_text.strip(),
                    ):
                        like_context["liked"] = False

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
                image_urls, video_urls, has_video = extract_feed_media(msg)
                # 提取转发内容
                rt_con = QzoneParser.extract_repost_text(msg.get("rt_con"))
                # 提取评论
                comments = Comment.build_list(msg.get("commentlist") or [])
                like_context = QzoneParser._like_context(
                    msg, msg.get("uin", 0), msg.get("tid", 0)
                )
                if html := msg.get("html"):
                    QzoneParser._apply_html_like_context(
                        bs4.BeautifulSoup(str(html), "html.parser"), like_context
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
                    has_video=has_video,
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
    def parse_recent_feeds(data: dict) -> tuple[list[Post], bool, str]:
        """解析最近说说列表，返回 (posts, has_more, cursor)"""
        page_meta = data.get("data", {}) if isinstance(data, dict) else {}
        raw_feeds = page_meta.get("data", []) if isinstance(page_meta, dict) else []
        feeds = raw_feeds if isinstance(raw_feeds, list) else []
        has_more_value = None
        for key in ("hasmore", "hasMore", "has_more", "hasMoreFeeds"):
            val = page_meta.get(key) if isinstance(page_meta, dict) else None
            if val is not None:
                has_more_value = QzoneParser._as_optional_bool(val)
                if has_more_value is not None:
                    break
        has_more = bool(feeds) if has_more_value is None else has_more_value
        cursor = ""
        for key in ("begintime", "attachinfo", "attach_info", "externparam"):
            val = page_meta.get(key) if isinstance(page_meta, dict) else None
            if val not in (None, ""):
                timestamp = QzoneParser.normalize_timestamp(val)
                if timestamp:
                    cursor = str(timestamp)
                    break
        if not data:
            return [], False, ""
        try:
            posts = []
            for feed in feeds:
                if not feed:
                    continue
                # 相册仅接受明确带有视频播放地址的动态。
                try:
                    appid = int(feed.get("appid"))
                except (TypeError, ValueError):
                    continue
                if appid <= 0:
                    continue
                uin = feed.get("uin", "")
                tid = feed.get("key", "")
                if not uin or not tid:
                    logger.error(f"无效的说说数据: target_qq={uin}, tid={tid}")
                    continue
                create_time = feed.get("abstime", "")
                nickname = (
                    feed.get("nickname", "")
                    or feed.get("name", "")
                    or (feed.get("userinfo") or {}).get("nickname", "")
                    or (feed.get("user") or {}).get("nickname", "")
                    or (feed.get("data") or {}).get("nickname", "")
                    or ((feed.get("data") or {}).get("user") or {}).get("nickname", "")
                    or ((feed.get("data") or {}).get("userinfo") or {}).get("nickname", "")
                )
                html_content = feed.get("html", "")
                if not html_content:
                    logger.error(f"说说内容为空: UIN={uin}, TID={tid}")
                    continue

                soup = bs4.BeautifulSoup(html_content, "html.parser")

                # 如果JSON字段中的昵称为空，从 HTML 中提取作者昵称
                if not nickname:
                    nick_link = soup.select_one("a.f-name[nickname], a.f-name[data-nick]")
                    if nick_link:
                        nickname = nick_link.get("nickname") or nick_link.get("data-nick") or ""
                    if not nickname:
                        nick_link = soup.select_one("a.f-name")
                        if nick_link:
                            nickname = nick_link.get_text(strip=True)
                    if not nickname:
                        nick_span = soup.select_one("span.f-name")
                        if nick_span:
                            nickname = nick_span.get_text(strip=True)
                    if not nickname and uin:
                        for a in soup.select("a"):
                            href = a.get("href", "")
                            if str(uin) in href and a.get_text(strip=True):
                                nickname = a.get_text(strip=True)
                                break
                text_div = soup.find("div", class_="f-info")
                text = text_div.get_text(strip=True) if text_div else ""
                # 提取转发内容
                rt_con = QzoneParser.extract_repost_html(soup)
                # 提取图片URL
                image_urls = []
                # 查找所有图片容器
                if img_box := soup.find("div", class_="img-box"):
                    for img in img_box.find_all("img"):  # type: ignore
                        if img.find_parent("div", class_="f-video-wrap"):
                            continue
                        src = img.get("src")  # type: ignore
                        if src and not str(src).startswith(
                            "http://qzonestyle.gtimg.cn"
                        ):  # 过滤表情图标
                            image_urls.append(src)
                # 获取视频url
                videos = []
                video_div = soup.select_one("div.img-box.f-video-wrap.play")
                if video_div and "url3" in video_div.attrs:
                    videos.append(video_div["url3"])
                if appid == 4 and not videos:
                    continue
                # 获取评论内容
                comments: list[Comment] = []
                # 查找所有评论项（包括主评论和回复）
                comment_items = soup.select("li.comments-item.bor3")
                if comment_items:
                    for item in comment_items:
                        # 提取基本信息
                        data_uin = str(item.get("data-uin", ""))
                        comment_tid = str(item.get("data-tid", ""))
                        comment_nickname = str(item.get("data-nick", ""))

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
                                nickname=comment_nickname,
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
                QzoneParser._apply_html_like_context(soup, like_context)

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
                    avatar_url=None,
                    text=text,
                    images=list(dict.fromkeys(image_urls)),
                    videos=videos,
                    has_video=video_div is not None,
                    create_time=create_time,
                    rt_con=rt_con,
                    comments=comments,
                    **like_context,
                )
                posts.append(post)

            if not cursor and not posts:
                timestamps = [
                    QzoneParser.normalize_timestamp(
                        feed.get("abstime")
                        or feed.get("created_time")
                        or feed.get("create_time")
                    )
                    for feed in feeds
                    if isinstance(feed, dict)
                ]
                timestamps = [timestamp for timestamp in timestamps if timestamp]
                if timestamps:
                    cursor = str(min(timestamps))

            logger.info(f"成功解析 {len(posts)} 条最新说说")
            return posts, has_more, cursor
        except Exception as e:
            logger.error(f"解析说说错误：{e}")
            return [], False, ""
