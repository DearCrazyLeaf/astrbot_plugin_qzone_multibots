from typing import Any
import json
from pathlib import Path

import aiohttp

from astrbot.api import logger

from ..config import PluginConfig
from .constants import (
    HTTP_STATUS_FORBIDDEN,
    HTTP_STATUS_UNAUTHORIZED,
    QZONE_CODE_IMAGE_EXPIRED,
    QZONE_CODE_LOGIN_EXPIRED,
    QZONE_CODE_UNKNOWN,
    QZONE_INTERNAL_HTTP_STATUS_KEY,
    QZONE_INTERNAL_META_KEY,
    QZONE_MSG_PERMISSION_DENIED,
)
from .parser import QzoneParser
from .session import QzoneSession


class QzoneHttpClient:
    def __init__(self, session: QzoneSession, config: PluginConfig):
        self.cfg = config
        self.session = session
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.cfg.connection.timeout)
        )

    async def close(self):
        await self._session.close()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: int | None = None,
        retry: int = 0,
    ) -> dict[str, Any]:
        ctx = await self.session.get_ctx()
        is_like = "internal_dolike_app" in url
        if is_like:
            logger.info(
                f"[QzoneLike] HTTP 请求 method={method} "
                f"endpoint={url.split('?')[0]} params_keys={sorted((params or {}).keys())} "
                f"data_keys={sorted((data or {}).keys())}"
            )
        async with self._session.request(
            method,
            url,
            params=params,
            data=data,
            headers=headers or ctx.headers(),
            cookies=ctx.cookies(),
            timeout=timeout,
        ) as resp:
            text = await resp.text()
        if is_like:
            summary = text[:240].replace("\n", " ")
            try:
                response_fields = json.loads(text) if text.strip() else {}
            except (TypeError, ValueError):
                response_fields = {}
            if not isinstance(response_fields, dict):
                response_fields = {}
            logger.info(
                f"[QzoneLike] HTTP 响应 account={ctx.uin} tid={(data or {}).get('fid', '')} "
                f"timestamp={(data or {}).get('abstime', '')} status={resp.status} "
                f"code={response_fields.get('code')} subcode={response_fields.get('subcode')} "
                f"retcode={response_fields.get('retcode')} message={response_fields.get('message')!r} "
                f"summary={summary!r}"
            )

        parsed = QzoneParser.parse_response(text, debug=self.cfg.debug_mode)
        meta = parsed.get(QZONE_INTERNAL_META_KEY)
        if not isinstance(meta, dict):
            meta = {}
            parsed[QZONE_INTERNAL_META_KEY] = meta
        meta[QZONE_INTERNAL_HTTP_STATUS_KEY] = resp.status

        # 仅在明确登录失效时触发重登
        # 注意：部分接口（点赞/评论）返回的 data 可能是 str/int/list，不能直接 .get
        _data = parsed.get("data")
        if not isinstance(_data, dict):
            _data = {}
        if (
            resp.status == HTTP_STATUS_UNAUTHORIZED
            or parsed.get("code") == QZONE_CODE_LOGIN_EXPIRED
            or _data.get("ret") == QZONE_CODE_IMAGE_EXPIRED
        ):
            if retry >= 2:
                raise RuntimeError("登录失效，重试失败")

            logger.warning("登录失效，重新登录中")
            await self.session.login()
            return await self.request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                retry=retry + 1,
            )

        if resp.status == HTTP_STATUS_FORBIDDEN and parsed.get("code") in (
            QZONE_CODE_UNKNOWN,
            None,
        ):
            parsed["code"] = resp.status
            parsed["message"] = QZONE_MSG_PERMISSION_DENIED

        return parsed
