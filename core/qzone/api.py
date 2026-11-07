import base64
import re
import time
from typing import Any
from urllib.parse import urlsplit

import json5
from astrbot.api import logger

from ..config import PluginConfig
from ..model import Comment, Post
from .client import QzoneHttpClient
from .constants import (
    QZONE_CODE_UNKNOWN,
    QZONE_INTERNAL_HTTP_STATUS_KEY,
    QZONE_INTERNAL_META_KEY,
    QZONE_MSG_EMPTY_RESPONSE,
    QZONE_MSG_INVALID_RESPONSE,
    QZONE_MSG_JSON_PARSE_ERROR,
    QZONE_MSG_NON_OBJECT_RESPONSE,
)
from .model import ApiResponse
from .parser import QzoneParser
from .session import QzoneSession
from .utils import normalize_images


class QzoneAPI(QzoneHttpClient):
    """QQ 空间 HTTP API 封装"""

    BASE_URL = "https://user.qzone.qq.com"
    UPLOAD_IMAGE_URL = "https://up.qzone.qq.com/cgi-bin/upload/cgi_upload_image"
    EMOTION_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6"
    DOLIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    DOLIKE_DIRECT_URL = "https://w.qzone.qq.com/cgi-bin/likes/internal_dolike_app"
    UNLIKE_URL = "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_unlike_app"
    UNLIKE_DIRECT_URL = "https://w.qzone.qq.com/cgi-bin/likes/internal_unlike_app"
    LIST_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
    COMMENT_URL = "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    COMMENT_H5_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
    ZONE_LIST_URL = "https://user.qzone.qq.com/proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/feeds3_html_more"
    REPLY_URL = COMMENT_H5_URL
    DELETE_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_delete_v6"
    DETAIL_URL = "https://h5.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msgdetail_v6"
    SHUOSHUO_URL = "https://h5.qzone.qq.com/webapp/json/mqzone_detail/shuoshuo"

    def __init__(self, session: QzoneSession, config: PluginConfig):
        super().__init__(session, config)

    @staticmethod
    def _social_action_response(raw: dict[str, Any]) -> ApiResponse:
        normalized = dict(raw)
        code = raw.get("code")
        if code is None:
            code = raw.get("ret", QZONE_CODE_UNKNOWN)
        try:
            normalized["code"] = int(code)
        except (TypeError, ValueError):
            normalized["code"] = QZONE_CODE_UNKNOWN
        return ApiResponse.from_raw(normalized)

    async def _upload_image(self, image: bytes) -> ApiResponse:
        """上传单张图片 (本接口较为脆弱)"""
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "POST",
            self.UPLOAD_IMAGE_URL,
            data={
                "filename": "filename",
                "uploadtype": "1",
                "albumtype": "7",
                "skey": ctx.skey,
                "uin": ctx.uin,
                "p_skey": ctx.p_skey,
                "output_type": "json",
                "base64": "1",
                "picfile": base64.b64encode(image).decode(),
            },
            headers={
                "referer": f"{self.BASE_URL}/{ctx.uin}",
                "origin": self.BASE_URL,
            },
            timeout=60,
        )
        if self.cfg.debug_mode:
            logger.debug(raw)
        return ApiResponse.from_raw(raw, code_key="ret", msg_key="msg")

    async def publish(self, post: Post) -> ApiResponse:
        """发表说说, 返回tid"""
        ctx = await self.session.get_ctx()
        data: dict[str, Any] = {
            "syn_tweet_verson": "1",
            "paramstr": "1",
            "who": "1",
            "con": post.text,
            "feedversion": "1",
            "ver": "1",
            "ugc_right": "1",
            "to_sign": "0",
            "hostuin": ctx.uin,
            "code_version": "1",
            "format": "json",
            "qzreferrer": f"{self.BASE_URL}/{ctx.uin}",
        }
        if post.images:
            if self.cfg.debug_mode:
                logger.debug(f"正在上传图片: {post.images}")
            pic_bos, richvals = [], []
            imgs: list[bytes] = await normalize_images(post.images)
            for img in imgs:
                resp = await self._upload_image(img)
                if not resp.ok:
                    raise RuntimeError(f"上传图片失败: {resp.message}")
                picbo, richval = QzoneParser.parse_upload_result(resp.data)
                pic_bos.append(picbo)
                richvals.append(richval)
            data.update(
                pic_bo=",".join(pic_bos),
                richtype="1",
                richval="\t".join(richvals),
            )

        raw = await self.request(
            "POST",
            self.EMOTION_URL,
            params={"g_tk": ctx.gtk2, "uin": ctx.uin},
            data=data,
        )
        return ApiResponse.from_raw(raw)

    async def like(
        self,
        post: Post,
        *,
        key_override: str | None = None,
        unlike: bool = False,
    ) -> ApiResponse:
        """
        点赞或取消点赞指定说说

        Args:
            post: 目标说说
            key_override: 可选的 key 覆盖
            unlike: 为 True 时发送取消点赞请求
        """
        ctx = await self.session.get_ctx()
        if not post.tid or not post.uin:
            raise ValueError("点赞目标缺少动态 ID 或作者 QQ 号")
        appid = int(post.appid or 311)
        if appid <= 0:
            raise ValueError("点赞目标缺少有效的动态应用 ID")
        bot_uin = ctx.uin

        action_text = "取消点赞" if unlike else "点赞"
        logger.info(
            f"[QzoneLikeDebug] 开始{action_text}: bot_uin={bot_uin}, "
            f"target_uin={post.uin}, tid={post.tid}, appid={appid}"
        )

        base_mood_key = f"{self.BASE_URL}/{post.uin}/mood/{post.tid}"
        fallback_key = (
            base_mood_key
            if appid == 311
            else ""
        )

        curkey = key_override or post.curkey or fallback_key
        unikey = key_override or post.unikey or fallback_key
        if appid != 311 and (not curkey or not unikey):
            raise ValueError("该类型动态缺少 QQ 返回的 curkey/unikey，无法构造点赞请求")

        if "/proxy/domain/" in curkey:
            curkey = curkey.split("/proxy/domain/")[-1]
            if not curkey.startswith("http"):
                curkey = f"{self.BASE_URL}/{curkey.lstrip('/')}"
        if "/proxy/domain/" in unikey:
            unikey = unikey.split("/proxy/domain/")[-1]
            if not unikey.startswith("http"):
                unikey = f"{self.BASE_URL}/{unikey.lstrip('/')}"

        if curkey.startswith("https://user.qzone.qq.com/"):
            curkey = curkey.replace("https://", "http://", 1)
        if unikey.startswith("https://user.qzone.qq.com/"):
            unikey = unikey.replace("https://", "http://", 1)
        if appid == 4 and ("/photo/" not in curkey.lower() or "/photo/" not in unikey.lower()):
            raise ValueError("相册动态点赞 key 缺少 /photo/ 路径")

        abstime = int(post.like_abstime or 0)
        like_typeid = int(post.like_typeid or (11 if appid == 4 else 0))

        logger.info(
            f"[QzoneLikeDebug] 最终构造: curkey={curkey}, unikey={unikey}, abstime={abstime}"
        )

        target_url = f"{self.BASE_URL}/{bot_uin}"
        request_headers = ctx.headers()
        request_headers.update(
            {
                "referer": target_url,
                "origin": self.BASE_URL,
            }
        )

        data = {
            "g_tk": ctx.gtk2,
            "qzreferrer": target_url,
            "opuin": bot_uin,
            "unikey": unikey,
            "curkey": curkey,
            "from": 1,
            "appid": appid,
            "typeid": like_typeid,
            "abstime": abstime,
            "fid": post.tid,
            "active": 0,
            "fupdate": 1,
        }

        endpoints = (
            (self.UNLIKE_URL, self.UNLIKE_DIRECT_URL)
            if unlike
            else (self.DOLIKE_URL, self.DOLIKE_DIRECT_URL)
        )

        parse_error_messages = {
            QZONE_MSG_EMPTY_RESPONSE,
            QZONE_MSG_INVALID_RESPONSE,
            QZONE_MSG_JSON_PARSE_ERROR,
            QZONE_MSG_NON_OBJECT_RESPONSE,
        }
        response = None
        last_error = None
        for endpoint in endpoints:
            try:
                endpoint_headers = dict(request_headers)
                endpoint_headers["Host"] = urlsplit(endpoint).netloc
                logger.info(f"[QzoneLikeDebug] 发起 HTTP 请求到 endpoint={endpoint}")
                raw = await self.request(
                    "POST",
                    endpoint,
                    params={"g_tk": ctx.gtk2},
                    data=data,
                    headers=endpoint_headers,
                )

                raw_meta = raw.get(QZONE_INTERNAL_META_KEY)
                raw_text = str((raw_meta or {}).get("raw_text") or "")
                logger.info(
                    f"[QzoneLikeDebug] 收到原始响应 raw_text_snippet={raw_text[:200]!r} parsed={raw}"
                )

                if "<!DOCTYPE html" in raw_text or "frameElement" in raw_text:
                    if m := re.search(r"(\{.*\})", raw_text, re.S):
                        try:
                            parsed_json = json5.loads(m.group(1))
                            if isinstance(parsed_json, dict):
                                raw = parsed_json
                                raw[QZONE_INTERNAL_META_KEY] = raw_meta
                        except Exception:
                            pass

                response = self._social_action_response(raw)
                meta = raw.get(QZONE_INTERNAL_META_KEY)
                http_status = (
                    meta.get(QZONE_INTERNAL_HTTP_STATUS_KEY)
                    if isinstance(meta, dict)
                    else None
                )
                parse_failed = (
                    response.code == QZONE_CODE_UNKNOWN
                    and response.message in parse_error_messages
                )
                if (
                    isinstance(http_status, int) and http_status >= 300
                ) or parse_failed:
                    last_error = RuntimeError(
                        f"点赞入口返回不可用响应: HTTP {http_status}, {response.message}"
                    )
                    logger.warning(
                        f"[QzoneLikeDebug] 入口不可用 endpoint={endpoint} "
                        f"status={http_status} message={response.message!r}"
                    )
                    response = None
                    continue
                break
            except Exception as exc:
                last_error = exc
                logger.warning(
                    f"[QzoneLikeDebug] 入口请求异常 endpoint={endpoint} "
                    f"type={type(exc).__name__}: {exc}"
                )
        if response is None:
            if last_error is not None:
                raise RuntimeError(
                    f"所有点赞入口均不可用: {last_error}"
                ) from last_error
            raise RuntimeError("所有点赞入口均不可用")
        logger.info(
            f"[QzoneLikeDebug] {action_text} API 最终响应 bot_uin={ctx.uin} "
            f"tid={post.tid} ok={response.ok} code={response.code} "
            f"message={response.message!r} data={response.data}"
        )
        return response

    async def comment(self, post: Post, content: str) -> ApiResponse:
        """
        评论指定说说
        """
        if not post.uin or not post.tid:
            raise ValueError("评论目标缺少动态 ID 或作者 QQ 号")
        if int(post.appid or 0) <= 0:
            raise ValueError("评论目标缺少有效的动态应用 ID")
        if not content.strip():
            raise ValueError("评论内容不能为空")

        ctx = await self.session.get_ctx()
        qzreferrer = f"{self.BASE_URL}/{ctx.uin}/main"
        request_data = (
            (
                self.COMMENT_URL,
                {
                    "hostUin": post.uin,
                    "topicId": f"{post.uin}_{post.tid}",
                    "content": content,
                    "format": "json",
                    "qzreferrer": qzreferrer,
                },
            ),
            (
                self.COMMENT_H5_URL,
                {
                    "topicId": f"{post.uin}_{post.tid}__1",
                    "uin": ctx.uin,
                    "hostUin": post.uin,
                    "feedsType": 100,
                    "inCharset": "utf-8",
                    "outCharset": "utf-8",
                    "plat": "qzone",
                    "source": "ic",
                    "platformid": 52,
                    "format": "fs",
                    "ref": "feeds",
                    "content": content,
                    "richval": "",
                    "richtype": "",
                    "private": "0",
                    "paramstr": "1",
                    "qzreferrer": qzreferrer,
                },
            ),
        )

        response: ApiResponse | None = None
        for index, (endpoint, data) in enumerate(request_data):
            raw = await self.request(
                "POST",
                endpoint,
                params={"g_tk": ctx.gtk2},
                data=data,
            )
            response = self._social_action_response(raw)
            if response.ok:
                return response

            meta = raw.get(QZONE_INTERNAL_META_KEY)
            http_status = (
                meta.get(QZONE_INTERNAL_HTTP_STATUS_KEY)
                if isinstance(meta, dict)
                else None
            )
            if index == 0 and (
                response.code != QZONE_CODE_UNKNOWN
                or (isinstance(http_status, int) and http_status >= 300)
            ):
                logger.warning(
                    f"PC 评论接口未受理请求，回退 H5 接口 "
                    f"status={http_status} code={response.code}"
                )
                continue
            return response

        if response is None:
            raise RuntimeError("QQ 空间评论接口未返回结果")
        return response

    async def reply(
        self,
        post: Post,
        comment: Comment,
        content: str,
    ) -> ApiResponse:
        """回复指定评论"""
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "POST",
            self.REPLY_URL,
            params={
                "g_tk": ctx.gtk2,
            },
            data={
                "topicId": f"{post.uin}_{post.tid}__1",
                "uin": ctx.uin,
                "hostUin": post.uin,
                "feedsType": 100,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "plat": "qzone",
                "source": "ic",
                "platformid": 52,
                "format": "fs",
                "ref": "feeds",
                "content": content,
                "commentId": comment.tid,
                "commentUin": comment.uin,
                "richval": "",  # 富文本内容
                "richtype": "",  # 富文本类型
                "private": "0",  # 是否私密评论
                "paramstr": "2",
                "qzreferrer": f"https://user.qzone.qq.com/{ctx.uin}/main",  # 来源页
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-site",
                "TE": "trailers",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
                "Referer": "https://user.qzone.qq.com/",
                "Origin": "https://user.qzone.qq.com",
            },
        )
        return self._social_action_response(raw)

    async def delete(self, tid: str) -> ApiResponse:
        """删除指定说说"""
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "POST",
            self.DELETE_URL,
            params={"g_tk": ctx.gtk2},
            data={
                "uin": ctx.uin,
                "topicId": f"{ctx.uin}_{tid}__1",
                "feedsType": 0,
                "feedsFlag": 0,
                "feedsKey": tid,
                "feedsAppid": 311,
                "feedsTime": int(time.time()),
                "fupdate": 1,
                "ref": "feeds",
                "qzreferrer": (
                    "https://user.qzone.qq.com/"
                    f"proxy/domain/ic2.qzone.qq.com/cgi-bin/feeds/"
                    f"feeds_html_module?g_iframeUser=1&i_uin={ctx.uin}&i_login_uin={ctx.uin}"
                    "&mode=4&previewV8=1&style=35&version=8"
                    "&needDelOpr=true"
                ),
            },
        )
        return ApiResponse.from_raw(raw)

    async def get_feeds(
        self,
        target_id: str,
        *,
        pos: int = 0,
        num: int = 1,
    ) -> ApiResponse:
        """
        获取指定QQ号的好友说说列表

        Args:
            target_id (str): 目标QQ号。
            pos (int): 起始位置。
            num (int): 要获取的说说数量。
        """
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "GET",
            self.LIST_URL,
            params={
                "g_tk": ctx.gtk2,
                "uin": target_id,  # 目标QQ
                "ftype": 0,  # 全部说说
                "sort": 0,  # 最新在前
                "pos": pos,  # 起始位置
                "num": num,  # 获取条数
                "replynum": 100,  # 评论数
                "callback": "_preloadCallback",
                "code_version": 1,
                "format": "json",
                "need_comment": 1,
                "need_private_comment": 1,
            },
        )
        return ApiResponse.from_raw(raw)

    async def get_detail(self, post: Post) -> ApiResponse:
        """
        获取单条说说详情（含完整评论、转发、图片、视频等）
        """
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "GET",
            self.DETAIL_URL,
            params={
                "uin": post.uin,
                "tid": post.tid,
                "num": 20,
                "pos": 0,
                "not_trunc_con": 1,
                "format": "json",
                "g_tk": ctx.gtk2,
            },
        )

        return ApiResponse.from_raw(raw)

    async def get_shuoshuo(self, post: Post) -> ApiResponse:
        """
        H5 shuoshuo 接口回读 (Ultra 兼容: detail 失败后回退)
        """
        ctx = await self.session.get_ctx()
        raw = await self.request(
            "GET",
            self.SHUOSHUO_URL,
            params={
                "cellid": post.tid,
                "uin": post.uin,
                "appid": int(post.appid or 311),
                "format": "json",
                "count": 20,
                "refresh_type": 31,
                "subid": "",
                "g_tk": ctx.gtk2,
            },
        )
        return ApiResponse.from_raw(raw)

    async def get_recent_feeds(
        self,
        page: int = 1,
        begintime: int | str = 0,
        *,
        target_id: str | None = None,
    ) -> ApiResponse:
        """
        获取自己的好友说说列表，返回已读与未读的说说列表
        """
        ctx = await self.session.get_ctx()
        params = {
            "uin": ctx.uin,  # 当前登录 QQ
            "scope": 0,  # 好友动态流
            "view": 1,  # 查看权限
            "filter": "all",  # 全部动态
            "flag": 1,  # 标记
            "applist": "all",  # 所有应用
            "pagenum": page,  # 页码
            "aisortEndTime": 0,
            "aisortOffset": 0,
            "aisortBeginTime": 0,
            "begintime": begintime,  # 开始时间，用于分页
            "format": "json",
            "g_tk": ctx.gtk2,
            "useutf8": 1,
            "outputhtmlfeed": 1,
        }
        if target_id:
            params["uinlist"] = str(target_id)

        raw = await self.request(
            "GET",
            self.ZONE_LIST_URL,
            params=params,
        )
        return ApiResponse.from_raw(raw)
