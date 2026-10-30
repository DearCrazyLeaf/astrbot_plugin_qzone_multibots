import time
from typing import Any

from astrbot.api import logger
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .db import PostDB
from .llm_action import LLMAction
from .model import Comment, LikeResult, Post
from .qzone import QzoneAPI, QzoneParser, QzoneSession
from .qzone.constants import (
    HTTP_STATUS_FORBIDDEN,
    QZONE_CODE_LOGIN_EXPIRED,
    QZONE_CODE_PERMISSION_DENIED,
    QZONE_CODE_PERMISSION_DENIED_LEGACY,
    QZONE_CODE_UNKNOWN,
    QZONE_INTERNAL_HTTP_STATUS_KEY,
    QZONE_INTERNAL_META_KEY,
    QZONE_MSG_EMPTY_RESPONSE,
    QZONE_MSG_INVALID_RESPONSE,
    QZONE_MSG_JSON_PARSE_ERROR,
    QZONE_MSG_NON_OBJECT_RESPONSE,
    QZONE_MSG_PERMISSION_DENIED,
)


class PostService:
    """
    Application Service 层
    """

    def __init__(
        self,
        qzone: QzoneAPI,
        session: QzoneSession,
        db: PostDB,
        llm: LLMAction,
    ):
        self.qzone = qzone
        self.session = session
        self.db = db
        self.llm = llm

    # ============================================================
    # 业务接口
    # ============================================================

    async def query_feeds(
        self,
        *,
        target_id: str | None = None,
        pos: int = 0,
        num: int = 1,
        with_detail: bool = False,
        no_self: bool = False,
        no_commented: bool = False,
        cursor: str = "",
    ) -> tuple[list[Post], bool, str]:
        if target_id:
            resp = await self.qzone.get_feeds(target_id, pos=pos, num=num)
            if not resp.ok:
                raise RuntimeError(self._map_feed_error(resp, target_id=target_id))
            msglist = resp.data.get("msglist") or []
            has_more = bool(resp.data.get("has_more", len(msglist) >= num))
            next_cursor = str(pos + len(msglist)) if msglist else ""
            if not msglist:
                logger.info(f"QQ {target_id} 暂无可见说说（非错误，返回空列表）")
                return [], has_more, next_cursor
            posts: list[Post] = QzoneParser.parse_feeds(
                msglist, debug=self.qzone.cfg.debug_mode
            )

        else:
            try:
                begintime = int(cursor) if cursor else 0
            except (TypeError, ValueError):
                begintime = 0
            resp = await self.qzone.get_recent_feeds(begintime=begintime)
            if not resp.ok:
                raise RuntimeError(self._map_feed_error(resp))
            all_posts, response_has_more, next_cursor = (
                QzoneParser.parse_recent_feeds(resp.data)
            )
            posts = all_posts[:num]
            has_more = response_has_more or len(all_posts) >= num
            if not next_cursor:
                times = [
                    int(p.create_time or 0)
                    for p in posts
                    if p.create_time and int(p.create_time) > 0
                ]
                if times:
                    next_cursor = str(min(times))
            if not posts:
                raise RuntimeError("动态流暂无可见说说")

        if no_self:
            uin = await self.session.get_uin()
            posts = [p for p in posts if p.uin != uin]

        if with_detail:
            posts = await self._fill_post_detail(posts)
            if not posts:
                raise RuntimeError("获取详情后无有效说说")

        if no_commented:
            posts = await self._filter_not_commented(posts)

        for post in posts:
            await self.db.save(post)

        return posts, has_more, next_cursor

    @staticmethod
    def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(k in text for k in keywords)

    def _map_feed_error(self, resp, *, target_id: str | None = None) -> str:
        message = str(resp.message or "").strip()
        lower_message = message.lower()
        code = resp.code
        http_status = self._extract_http_status(resp.raw)

        permission_keywords = (
            "无权限",
            "权限",
            "私密",
            "不可见",
            "拒绝访问",
            "受限",
            "forbidden",
            QZONE_MSG_PERMISSION_DENIED,
            "access denied",
        )
        login_keywords = ("登录", "失效", "skey", "g_tk", "cookie", "expired")

        if code == QZONE_CODE_LOGIN_EXPIRED or self._contains_any(
            lower_message, login_keywords
        ):
            return "登录状态失效，请重新登录后重试"

        if (
            code in (QZONE_CODE_PERMISSION_DENIED, QZONE_CODE_PERMISSION_DENIED_LEGACY)
            or http_status == HTTP_STATUS_FORBIDDEN
            or self._contains_any(lower_message, permission_keywords)
        ):
            if target_id:
                return f"无权限查看 QQ {target_id} 的说说"
            return "无权限访问动态流"

        if code == QZONE_CODE_UNKNOWN and message == QZONE_MSG_EMPTY_RESPONSE:
            if target_id:
                return f"无权限查看 QQ {target_id} 的说说（接口返回空响应）"
            return "动态接口返回空响应，请稍后重试"

        if code == QZONE_CODE_UNKNOWN and message in (
            QZONE_MSG_INVALID_RESPONSE,
            QZONE_MSG_JSON_PARSE_ERROR,
            QZONE_MSG_NON_OBJECT_RESPONSE,
        ):
            return "接口响应格式异常，请稍后重试"

        if message:
            return f"查询说说失败：{message}"
        return f"查询说说失败：code={code}"

    @staticmethod
    def _extract_http_status(raw: dict[str, Any]) -> int | None:
        meta = raw.get(QZONE_INTERNAL_META_KEY)
        if not isinstance(meta, dict):
            return None
        status = meta.get(QZONE_INTERNAL_HTTP_STATUS_KEY)
        return status if isinstance(status, int) else None

    @staticmethod
    def _has_comment_from_uin(post: Post, uin: int) -> bool:
        return any(comment.uin == uin for comment in post.comments)

    @staticmethod
    def _merge_post_reference(source: Post, target: Post) -> Post:
        """Keep list-feed like references when the detail response omits them."""
        if not target.appid:
            target.appid = source.appid or 311
        target.curkey = target.curkey or source.curkey
        target.unikey = target.unikey or source.unikey
        target.like_abstime = target.like_abstime or source.like_abstime
        target.create_time = target.create_time or source.create_time
        if target.liked is None:
            target.liked = source.liked
        if not target.like_count:
            target.like_count = source.like_count
        return target

    async def _has_saved_self_comment(self, post: Post, uin: int) -> bool:
        if not post.tid:
            return False
        saved_post = await self.db.get(post.tid, key="tid")
        return bool(saved_post and self._has_comment_from_uin(saved_post, uin))

    async def _fill_post_detail(self, posts: list[Post]) -> list[Post]:
        result: list[Post] = []

        for post in posts:
            resp = await self.qzone.get_detail(post)
            if not resp.ok or not resp.data:
                logger.warning(f"获取详情失败：{resp.data}")
                continue

            parsed = QzoneParser.parse_feeds(
                [resp.data], debug=self.qzone.cfg.debug_mode
            )
            if not parsed:
                logger.warning(f"解析详情失败：{resp.data}")
                continue

            result.append(self._merge_post_reference(post, parsed[0]))

        return result

    async def _filter_not_commented(self, posts: list[Post]) -> list[Post]:
        result: list[Post] = []
        uin = await self.session.get_uin()

        for post in posts:
            if self._has_comment_from_uin(post, uin):
                continue
            if await self._has_saved_self_comment(post, uin):
                continue

            # 如果已经有 comments，说明是 detail post
            if not post.comments:
                resp = await self.qzone.get_detail(post)
                if not resp.ok or not resp.data:
                    continue
                parsed = QzoneParser.parse_feeds(
                    [resp.data], debug=self.qzone.cfg.debug_mode
                )
                if not parsed:
                    continue
                post = self._merge_post_reference(post, parsed[0])

            if self._has_comment_from_uin(post, uin):
                continue

            result.append(post)

        return result

    # ==================== 对外接口 ========================

    async def like_posts(self, post: Post, *, unlike: bool = False):
        """点赞或取消点赞指定动态 (多 BOT 隔离加固版)

        Args:
            post: 目标动态
            unlike: 为 True 时发送取消点赞请求
        """
        if not post.tid or not post.uin:
            return LikeResult(
                status="rejected",
                liked=None,
                verified=False,
                message="点赞目标缺少动态 ID 或作者 QQ 号",
            )

        actor_uin = await self.session.get_uin()

        try:
            logger.info(
                f"[QzoneLikeMultiBot] service 开始 actor_uin={actor_uin} "
                f"target_uin={post.uin} tid={post.tid} appid={post.appid}"
            )

            response = await self.qzone.like(post, unlike=unlike)
            if not response.ok:
                return LikeResult(
                    status="rejected",
                    liked=None,
                    verified=False,
                    message=str(response.message or "点赞接口拒绝请求"),
                )

            logger.info(
                f"[QzoneLikeMultiBot] service 接口已受理 actor_uin={actor_uin} tid={post.tid}"
            )

            target_liked = not unlike
            post.liked = target_liked
            action_text = "取消点赞" if unlike else "点赞"
            logger.info(
                f"[QzoneLikeMultiBot] service 完成 actor_uin={actor_uin} "
                f"tid={post.tid} liked={post.liked} verified=False action={action_text}"
            )
            return LikeResult(
                status="accepted_unverified",
                liked=target_liked,
                verified=False,
                message=f"{action_text}请求已提交到 QQ 空间，稍后可能需要刷新查看最新状态",
            )
        except Exception as exc:
            logger.exception(
                f"[QzoneLikeMultiBot] service 异常 actor_uin={actor_uin} tid={post.tid}"
            )
            return LikeResult(
                status="rejected",
                liked=post.liked,
                verified=False,
                message=str(exc) or "点赞请求失败",
            )

    async def comment_posts(
        self,
        post: Post,
        event: AiocqhttpMessageEvent | None = None,
        *,
        umo: str | None = None,
    ) -> str:
        """评论帖子"""
        if not post.tid:
            raise ValueError("帖子 tid 为空")

        content = await self.llm.generate_comment(post, event=event, umo=umo)
        if not content:
            raise ValueError("生成评论内容为空")

        resp = await self.qzone.comment(post, content)
        if not resp.ok:
            raise RuntimeError(resp.message)

        uin = await self.session.get_uin()
        name = await self.session.get_nickname()
        post.comments.append(
            Comment(
                uin=uin,
                nickname=name,
                content=content,
                create_time=int(time.time()),
                tid=0,
                parent_tid=None,
            )
        )
        await self.db.save(post)
        logger.info(f"评论 → {post.name}")
        return content

    async def reply_to_comment(
        self,
        post: Post,
        comment: Comment,
        *,
        event: AiocqhttpMessageEvent | None = None,
        umo: str | None = None,
    ) -> str:
        """直接回复指定评论，供后台轮询处理新评论。"""
        if not post.tid or not comment.tid:
            raise ValueError("说说或评论 ID 为空")
        content = await self.llm.generate_reply(post, comment, event=event, umo=umo)
        if not content:
            raise ValueError("生成回复内容为空")
        resp = await self.qzone.reply(post, comment, content)
        if not resp.ok:
            raise RuntimeError(resp.message)
        uin = await self.session.get_uin()
        name = await self.session.get_nickname()
        post.comments.append(
            Comment(
                uin=uin,
                nickname=name,
                content=content,
                create_time=int(time.time()),
                parent_tid=comment.tid,
            )
        )
        await self.db.save(post)
        logger.info(f"回复 → {comment.nickname}")
        return content

    async def publish_post(
        self,
        *,
        post: Post | None = None,
        text: str | None = None,
        images: list | None = None,
    ) -> Post:
        """发表帖子（支持 Post / text / images，但不能为空）"""

        # 参数校验
        if post is None and not text and not images:
            raise ValueError("post、text、images 不能同时为空")

        # 如果没传 post，就自动构造一个
        if post is None:
            uin = await self.session.get_uin()
            name = await self.session.get_nickname()
            post = Post(
                uin=uin,
                name=name,
                text=text or "",
                images=images or [],
            )

        # 发布
        resp = await self.qzone.publish(post)
        if not resp.ok:
            raise RuntimeError(f"发布说说失败：{resp.data}")

        # 回填发布结果
        post.tid = resp.data.get("tid")
        post.status = "approved"
        post.create_time = resp.data.get("now", post.create_time)
        post.like_abstime = QzoneParser.normalize_timestamp(post.create_time)

        # 持久化
        await self.db.save(post)
        return post
