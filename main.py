import base64
import random
from typing import Any

from astrbot.api import logger
from astrbot.api.event import filter
from astrbot.api.star import Context, Star
from astrbot.core import AstrBotConfig
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)

from .core.config import PluginConfig
from .core.db import PostDB
from .core.llm_action import LLMAction
from .core.model import Comment, Post
from .core.qzone import QzoneAPI, QzoneParser, QzoneSession
from .core.sender import Sender
from .core.poller import QzonePoller
from .core.service import PostService
from .core.utils import get_image_urls

try:
    from quart import jsonify as _quart_jsonify
    from quart import request as _quart_request
except Exception:
    _quart_jsonify = None
    _quart_request = None


class QzonePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context = context
        self.cfg = PluginConfig(config, context)
        self.sessions: dict[str, QzoneSession] = {}
        self.qzones: dict[str, QzoneAPI] = {}
        self.services: dict[str, PostService] = {}
        self.db = PostDB(self.cfg)
        self.llm = LLMAction(self.cfg)
        self.sender = Sender(self.cfg)
        self.poller = None
        self._page_post_refs: dict[str, tuple[str, Post]] = {}
        self._register_page_web_apis()

    def _platforms(self) -> dict[str, Any]:
        result = {}
        for platform in getattr(self.context.platform_manager, "platform_insts", []):
            try:
                meta = platform.meta()
                name = str(getattr(meta, "id", "") or "")
                if not name:
                    name = str(
                        getattr(platform, "config", {}).get("id", "")
                        if isinstance(getattr(platform, "config", None), dict)
                        else ""
                    )
                if not name:
                    name = str(getattr(meta, "name", ""))
                if name and str(getattr(meta, "name", "")) == "aiocqhttp":
                    if name in result:
                        logger.warning(
                            f"[Qzone] 检测到重名的 aiocqhttp 平台实例 '{name}'，"
                            "后者会覆盖前者。请检查 WebUI 平台适配中两个实例的平台名是否相同"
                        )
                    result[name] = platform
            except Exception:
                continue
        self._debug_log(
            f"当前识别到 {len(result)} 个 aiocqhttp 平台实例: {list(result)}"
        )
        return result

    def _ensure_accounts(self) -> None:
        for name, platform in self._platforms().items():
            if name in self.sessions:
                continue
            bot = getattr(platform, "bot", None)
            if bot is None:
                logger.warning(
                    f"[Qzone] 平台实例 '{name}' 尚未连接（bot 为空），跳过建会话，"
                    "连接成功后下次调用会自动补建"
                )
                continue
            session = QzoneSession(self.cfg)
            session.client = bot
            self.sessions[name] = session
            self.qzones[name] = QzoneAPI(session, self.cfg)
            self.services[name] = PostService(self.qzones[name], session, self.db, self.llm)
            self._debug_log(
                f"已为平台实例 '{name}' 建立 Qzone 会话，当前会话池: {list(self.sessions)}"
            )

    def _account_name(self, event=None, requested: str | None = None) -> str:
        self._ensure_accounts()
        if requested and requested in self.services:
            return requested
        if event is not None:
            for attr in ("get_platform_name",):
                getter = getattr(event, attr, None)
                if callable(getter):
                    try:
                        name = str(getter())
                        if name in self.services:
                            return name
                    except Exception:
                        pass
            umo = str(getattr(event, "unified_msg_origin", ""))
            prefix = umo.split(":", 1)[0]
            if prefix in self.services:
                return prefix
            bot = getattr(event, "bot", None)
            for name, platform in self._platforms().items():
                if getattr(platform, "bot", None) is bot:
                    return name
        if len(self.services) == 1:
            return next(iter(self.services))
        if self.services:
            return next(iter(self.services))
        raise RuntimeError("没有可用的 aiocqhttp 账号")

    def _account(self, event=None, requested: str | None = None):
        name = self._account_name(event, requested)
        session = self.sessions[name]
        session.client = getattr(self._platforms().get(name), "bot", None) or session.client
        return name, session, self.qzones[name], self.services[name]

    async def initialize(self):
        await self.db.initialize()
        self._ensure_accounts()
        if not self.cfg.trigger.auto_enabled:
            logger.info("自动触发总开关关闭，概率互动与空间轮询均未启动")
        elif self.cfg.polling.enabled:
            self.poller = QzonePoller(self)
            await self.poller.register()

    def _register_page_web_apis(self) -> None:
        routes = (
            ("page/accounts", self.page_accounts, ["GET"], "Qzone dashboard accounts"),
            ("page/status", self.page_status, ["GET"], "Qzone dashboard status"),
            ("page/feed", self.page_feed, ["GET"], "Qzone dashboard feed"),
            ("page/detail", self.page_detail, ["GET"], "Qzone dashboard detail"),
            ("page/publish", self.page_publish, ["POST"], "Qzone dashboard publish"),
            ("page/like", self.page_like, ["POST"], "Qzone dashboard like"),
            ("page/comment", self.page_comment, ["POST"], "Qzone dashboard comment"),
            ("page/reply", self.page_reply, ["POST"], "Qzone dashboard reply"),
            ("page/delete", self.page_delete, ["POST"], "Qzone dashboard delete"),
            (
                "page/upload-media",
                self.page_upload_media,
                ["POST"],
                "Qzone dashboard upload media",
            ),
            ("page/debug", self.page_debug, ["GET"], "Qzone dashboard debug toggle"),
        )
        for endpoint, handler, methods, desc in routes:
            self.context.register_web_api(
                f"/astrbot_plugin_qzone_multibots/{endpoint}",
                handler,
                methods,
                desc,
            )

    def _debug_log(self, message: str) -> None:
        """仅当调试模式开启时输出调试日志"""
        if getattr(self.cfg, "debug_mode", False):
            logger.debug(f"[Qzone] {message}")

    async def page_debug(self):
        """查询或切换调试模式"""
        async def handler():
            enable = (await self._page_query_params()).get("enable")
            if enable is not None:
                self.cfg.debug_mode = str(enable).strip().lower() in ("1", "true", "yes", "on")
                self.cfg.save_config()
                self._debug_log("调试模式已通过 WebUI 开关更新")
            return {"ok": True, "data": {"debug": bool(getattr(self.cfg, "debug_mode", False))}}
        return await self._page_json(handler)

    async def _page_response(self, payload: dict, status: int = 200):
        if _quart_jsonify is None:
            return payload
        response = _quart_jsonify(payload)
        response.status_code = status
        return response

    async def _page_json(self, callback):
        try:
            payload = await callback()
            status = 200
        except Exception as exc:
            logger.exception("qzone page api failed: %s", exc)
            payload = {
                "ok": False,
                "error": {
                    "message": str(exc) or "请求失败",
                },
            }
            status = 400
        return await self._page_response(payload, status)

    async def _page_query_params(self) -> dict:
        if _quart_request is None:
            return {}
        args = getattr(_quart_request, "args", {}) or {}
        try:
            return {str(key): value for key, value in args.items()}
        except Exception:
            return dict(args)

    async def _page_json_body(self) -> dict:
        if _quart_request is None:
            return {}
        try:
            data = await _quart_request.get_json(silent=True)
        except TypeError:
            data = await _quart_request.get_json()
        return data if isinstance(data, dict) else {}

    async def _build_page_status(self, account: str | None = None) -> dict:
        name, session, _, _ = self._account(requested=account)
        try:
            uin = await session.get_uin()
            nickname = await session.get_nickname()
            bound = True
        except Exception:
            uin, nickname, bound = 0, "", False
        return {"ok": True, "data": {"daemon": {"state": "ready" if bound else "offline"}, "login": {"bound": bound, "uin": uin, "nickname": nickname, "avatar": ""}, "account": name, "limits": {"feed": 10, "images": 9}}}

    def _remember_page_post(self, post: Post, account: str = "") -> str:
        post_id = f"{post.uin}:{post.tid}"
        self._page_post_refs[post_id] = (account, post)
        return post_id

    def _page_post_payload(
        self,
        post: Post,
        *,
        include_comments: bool = False,
        self_uin: int = 0,
        account: str = "",
    ) -> dict:
        images = list(dict.fromkeys([*(post.images or []), *(post.videos or [])]))
        payload = {
            "id": self._remember_page_post(post, account),
            "author": {
                "uin": post.uin,
                "nickname": post.name or str(post.uin),
                "avatar": post.avatar_url or "",
            },
            "content": post.text or post.rt_con or "",
            "created_at": int(post.create_time or 0),
            "stats": {
                "likes": 0,
                "comments": len(post.comments or []),
            },
            "liked": False,
            "images": images,
            "can_delete": bool(self_uin and int(post.uin) == int(self_uin)),
        }
        if include_comments:
            payload["comments"] = [
                {
                    "id": str(comment.tid or index),
                    "author": {
                        "uin": comment.uin,
                        "nickname": comment.nickname or str(comment.uin),
                    },
                    "content": comment.content,
                    "created_at": int(comment.create_time or 0),
                    "can_reply": bool(comment.tid and comment.uin),
                }
                for index, comment in enumerate(post.comments or [], start=1)
            ]
        return payload

    def _require_page_post(self, post_id: str, account: str | None = None) -> Post:
        ref = self._page_post_refs.get(str(post_id or "").strip())
        if not ref:
            raise RuntimeError("说说引用已失效，请刷新页面后重试")
        ref_account, post = ref
        if account and ref_account and account != ref_account:
            raise RuntimeError("该说说不属于当前账号")
        return post

    async def page_accounts(self):
        async def handler():
            self._ensure_accounts()
            accounts = []
            for name, session in self.sessions.items():
                try:
                    uin, nickname = await session.get_uin(), await session.get_nickname()
                    bound = True
                except Exception as exc:
                    logger.warning(f"[Qzone] 账号 '{name}' 获取 Cookie 失败: {exc}")
                    uin, nickname, bound = 0, "", False
                logger.info(
                    f"[Qzone] 账号 '{name}' 状态: bound={bound}, uin={uin}, "
                    f"会话池共 {len(self.sessions)} 个账号"
                )
                login_uin, login_nick = 0, ""
                try:
                    if getattr(session, "client", None) is not None:
                        info = await session.client.get_login_info()
                        login_uin = int(info.get("user_id") or 0)
                        login_nick = str(info.get("nickname") or "")
                except Exception as exc:
                    self._debug_log(f"账号 '{name}' get_login_info 失败: {exc}")
                self._debug_log(
                    f"账号 '{name}' 状态: bound={bound}, uin={uin}, nickname={nickname}, "
                    f"login_uin={login_uin}, login_nick={login_nick}"
                )
                accounts.append({
                    "id": name, "name": name, "uin": uin, "nickname": nickname, "bound": bound,
                    "login_uin": login_uin, "login_nick": login_nick,
                })
            return {"ok": True, "data": {"items": accounts}}
        return await self._page_json(handler)

    async def page_status(self):
        async def handler():
            params = await self._page_query_params()
            return await self._build_page_status(params.get("account"))
        return await self._page_json(handler)

    async def page_feed(self):
        async def handler():
            params = await self._page_query_params()
            name, session, qzone, service = self._account(requested=params.get("account"))
            params = await self._page_query_params()
            scope = str(params.get("scope") or "friends")
            self_uin = await session.get_uin()
            target_id = None
            no_self = False
            if scope == "self":
                target_id = str(self_uin)
            elif scope == "profile":
                target_id = str(params.get("hostuin") or "").strip() or None
            else:
                no_self = False
            posts = await service.query_feeds(
                target_id=target_id,
                pos=0,
                num=min(max(int(params.get("limit") or 10), 1), 10),
                with_detail=False,
                no_self=no_self,
            )
            return {
                "ok": True,
                "data": {
                    "items": [
                        self._page_post_payload(post, self_uin=self_uin, account=name)
                        for post in posts
                    ],
                    "cursor": "",
                    "has_more": False,
                },
            }

        return await self._page_json(handler)

    async def page_detail(self):
        async def handler():
            params = await self._page_query_params()
            name, session, qzone, service = self._account(requested=params.get("account"))
            post = self._require_page_post(params.get("id", ""), params.get("account"))
            resp = await qzone.get_detail(post)
            if not resp.ok or not resp.data:
                raise RuntimeError(resp.message or "获取详情失败")
            parsed = QzoneParser.parse_feeds([resp.data])
            matched = parsed[0] if parsed else post
            self._remember_page_post(matched, name)
            return {
                "ok": True,
                "data": {
                    "post": self._page_post_payload(
                        matched,
                        include_comments=True,
                        self_uin=await session.get_uin(),
                        account=name,
                    )
                },
            }

        return await self._page_json(handler)

    async def page_publish(self):
        async def handler():
            body = await self._page_json_body()
            name, session, qzone, service = self._account(requested=body.get("account"))
            media = body.get("media") or []
            images = []
            for item in media:
                if not isinstance(item, dict):
                    continue
                source = str(item.get("source") or "")
                if source.startswith("base64://"):
                    images.append(base64.b64decode(source.removeprefix("base64://")))
            post = await service.publish_post(
                text=str(body.get("content") or ""),
                images=images,
            )
            return {
                "ok": True,
                "data": {"post": self._page_post_payload(post, account=name)},
                "message": "说说已发布。",
            }

        return await self._page_json(handler)

    async def page_like(self):
        async def handler():
            body = await self._page_json_body()
            name, session, qzone, service = self._account(requested=body.get("account"))
            post = self._require_page_post(body.get("id", ""), body.get("account"))
            resp = await qzone.like(post)
            if not resp.ok:
                raise RuntimeError(resp.message or "点赞失败")
            return {"ok": True, "data": {"liked": True, "verified": True}}

        return await self._page_json(handler)

    async def page_comment(self):
        async def handler():
            body = await self._page_json_body()
            name, session, qzone, service = self._account(requested=body.get("account"))
            post = self._require_page_post(body.get("id", ""), body.get("account"))
            content = str(body.get("content") or "").strip()
            if not content:
                raise RuntimeError("评论内容不能为空")
            resp = await qzone.comment(post, content)
            if not resp.ok:
                raise RuntimeError(resp.message or "评论失败")
            comment = {
                "id": f"local-{len(post.comments) + 1}",
                "content": content,
                "author": {
                    "uin": await session.get_uin(),
                    "nickname": await session.get_nickname(),
                    "avatar": "",
                },
            }
            post.comments.append(
                Comment(
                    uin=comment["author"]["uin"],
                    nickname=comment["author"]["nickname"],
                    content=content,
                    create_time=0,
                    tid=0,
                    parent_tid=None,
                )
            )
            return {"ok": True, "data": {"comment": comment}, "message": "评论已发送。"}

        return await self._page_json(handler)

    async def page_reply(self):
        async def handler():
            body = await self._page_json_body()
            name, session, qzone, service = self._account(requested=body.get("account"))
            post = self._require_page_post(body.get("id", ""), body.get("account"))
            content = str(body.get("content") or "").strip()
            comment_id = str(body.get("commentid") or "")
            if not content:
                raise RuntimeError("回复内容不能为空")
            target = next(
                (item for item in post.comments if str(item.tid) == comment_id), None
            )
            if target is None:
                raise RuntimeError("未找到要回复的评论")
            resp = await qzone.reply(post, target, content)
            if not resp.ok:
                raise RuntimeError(resp.message or "回复失败")
            reply = {
                "id": str(resp.data.get("tid") or ""),
                "content": content,
                "author": {
                    "uin": await session.get_uin(),
                    "nickname": await session.get_nickname(),
                    "avatar": "",
                },
            }
            post.comments.append(
                Comment(
                    uin=reply["author"]["uin"],
                    nickname=reply["author"]["nickname"],
                    content=content,
                    create_time=0,
                    tid=int(reply["id"]) if reply["id"].isdigit() else 0,
                    parent_tid=target.tid,
                )
            )
            return {"ok": True, "data": {"reply": reply}, "message": "回复已发送。"}

        return await self._page_json(handler)

    async def page_delete(self):
        async def handler():
            body = await self._page_json_body()
            name, session, qzone, service = self._account(requested=body.get("account"))
            post = self._require_page_post(body.get("id", ""), body.get("account"))
            self_uin = await session.get_uin()
            if int(post.uin) != int(self_uin):
                raise RuntimeError("只能删除自己发布的说说")
            resp = await qzone.delete(str(post.tid or ""))
            if not resp.ok:
                raise RuntimeError(resp.message or "删除失败")
            return {"ok": True, "data": {}, "message": "说说已删除。"}

        return await self._page_json(handler)

    async def page_upload_media(self):
        async def handler():
            if _quart_request is None:
                raise RuntimeError("当前环境不支持上传")
            files = await _quart_request.files
            upload = files.get("file") or files.get("image") or files.get("media")
            if upload is None:
                raise RuntimeError("没有收到图片文件")
            data = await upload.read()
            return {
                "ok": True,
                "data": {
                    "media": {
                        "kind": "image",
                        "name": upload.filename or "image.jpg",
                        "source": f"base64://{base64.b64encode(data).decode('ascii')}",
                        "size": len(data),
                        "mime_type": getattr(upload, "content_type", "")
                        or "image/jpeg",
                    }
                },
            }

        return await self._page_json(handler)

    async def terminate(self):
        """插件卸载时"""
        if self.poller is not None:
            await self.poller.close()
        for qzone in self.qzones.values():
            await qzone.close()

    @filter.platform_adapter_type(filter.PlatformAdapterType.AIOCQHTTP)
    async def prob_read_feed(self, event: AiocqhttpMessageEvent):
        """监听消息"""
        if not self.cfg.trigger.auto_enabled:
            return

        group_id = str(event.get_group_id() or "")
        if group_id and self.cfg.source.is_ignore_group(group_id):
            return

        self._account(event)

        # 按概率触发点赞+评论
        sender_id = event.get_sender_id()
        if (
            not self.cfg.source.is_ignore_user(sender_id)
            and random.random() < self.cfg.trigger.read_prob
        ):
            target_id = event.get_sender_id()
            posts = await self._account(event)[3].query_feeds(
                target_id=target_id, pos=0, num=1, no_self=True, no_commented=True
            )
            for post in posts:
                try:
                    comment = await self._account(event)[3].comment_posts(
                        post, event=event
                    )
                    if self.cfg.trigger.like_when_comment:
                        await self._account(event)[3].like_posts(post)
                    await self.sender.send_post(
                        event,
                        post,
                        message=f"触发读说说\n实际评论：{comment}",
                        send_admin=self.cfg.trigger.send_admin,
                    )
                except Exception as e:
                    logger.error(e)


    @filter.llm_tool()
    async def llm_view_feed(
        self,
        event: AiocqhttpMessageEvent,
        user_id: str | None = None,
        pos: int = 0,
        like: bool = False,
        reply: bool = False,
    ):
        """
        查看、点赞、评论某位用户QQ空间的某条说说、动态
        Args:
            user_id(string): 目标用户的QQ账号，必定为一串数字，如(12345678), 默认为当前用户QQ号
            pos(number): 要查询的说说序号, 默认为0表示最新
            like(boolean): 是否点赞
            reply(boolean): 是否评论
        """
        try:
            user_id = user_id or event.get_sender_id()
            self._debug_log(f"正在查询用户（{user_id}）的第 {pos} 条说说")

            posts = await self._account(event)[3].query_feeds(
                target_id=user_id,
                pos=pos,
                num=1,
                with_detail=True,
            )

            if not posts:
                return "查询结果为空"

            post = posts[0]

            # 执行动作
            msg = ""

            if like and reply:
                await self._account(event)[3].comment_posts(post, event=event)
                await self._account(event)[3].like_posts(post)
                msg = "已评论并点赞"
            elif reply:
                await self._account(event)[3].comment_posts(post, event=event)
                msg = "已评论"
            elif like:
                await self._account(event)[3].like_posts(post)
                msg = "已点赞"

            # 发送展示
            await self.sender.send_post(event, post, message=msg)

            return msg + "\n" + post.text + "\n" + "\n".join(post.images)

        except Exception as e:
            logger.error(e)
            return str(e)

    @filter.llm_tool()
    async def llm_publish_feed(
        self,
        event: AiocqhttpMessageEvent,
        text: str = "",
        get_image: bool = True,
    ):
        """
        写一篇说说并发布到QQ空间
        Args:
            text(string): 要发布的说说内容
            get_image(boolean): 是否获取当前对话中的图片附加到说说里, 默认为True
        """
        images = await get_image_urls(event) if get_image else []
        try:
            post = await self._account(event)[3].publish_post(text=text, images=images)
            await self.sender.send_post(event, post, message="已发布")
            return "已发布说说到QQ空间: \n" + post.text + "\n" + "\n".join(post.images)
        except Exception as e:
            return str(e)

    @filter.llm_tool()
    async def llm_qzone_status(self, event: AiocqhttpMessageEvent):
        """
        查询所有挂载账号的QQ空间登录状态。会强制逐账号获取（或刷新）Cookie，
        返回每个账号是否已成功绑定空间登录。执行任何QQ空间操作前可先调用本工具确认。
        """
        self._ensure_accounts()
        if not self.sessions:
            return "未识别到任何 aiocqhttp 平台实例，请检查平台适配配置"
        lines = []
        for name, session in self.sessions.items():
            try:
                uin = await session.get_uin()
                lines.append(f"[{name}] 已登录，uin={uin}")
            except Exception as e:
                lines.append(f"[{name}] 未登录/获取Cookie失败: {e}")
        return "共 %d 个账号：\n%s" % (len(self.sessions), "\n".join(lines))
