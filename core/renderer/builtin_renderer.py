from __future__ import annotations

import asyncio
from pathlib import Path

from ..config import PluginConfig
from ..model import Post
from .parser_card_renderer import Renderer as ParserCardRenderer
from .post_adapter import QzonePostCardAdapter
from .resource_fetcher import ResourceFetcher


class BuiltinQzoneCardRenderer:
    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.fetcher = ResourceFetcher(config)
        self.adapter = QzonePostCardAdapter(self.fetcher)
        self.renderer = ParserCardRenderer(config)
        self._resources_loaded = False

    async def _ensure_resources_loaded(self) -> None:
        if self._resources_loaded:
            return
        await asyncio.to_thread(ParserCardRenderer.load_resources)
        self._resources_loaded = True

    async def render_post(self, post: Post) -> Path | None:
        await self._ensure_resources_loaded()
        result = await self.adapter.to_parse_result(post)
        return await self.renderer.render_card(result)
