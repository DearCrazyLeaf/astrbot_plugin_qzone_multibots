from astrbot.api import logger
from astrbot.core.message.components import BaseMessageComponent, Image, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from .config import PluginConfig
from .model import Post
from .renderer import BuiltinQzoneCardRenderer


class Sender:
    def __init__(self, config: PluginConfig):
        self.cfg = config
        self.renderer = BuiltinQzoneCardRenderer(config)

    async def _post_to_seg(self, post: Post) -> BaseMessageComponent:
        image_path = await self.renderer.render_post(post)
        if image_path:
            return Image.fromFileSystem(str(image_path))
        return Plain(post.to_str())

    async def _text_to_seg(self, text: str) -> BaseMessageComponent:
        image_path = await self.renderer.render_text(text)
        if image_path:
            return Image.fromFileSystem(str(image_path))
        return Plain(text)

    async def _send_chain(
        self,
        event: AstrMessageEvent,
        *segments: BaseMessageComponent,
    ) -> None:
        await event.send(event.chain_result(list(segments)))

    async def send_post(
        self,
        event: AstrMessageEvent,
        post: Post,
        *,
        message: str = "",
        send_admin: bool = False,
    ):
        if send_admin and self.cfg.admin_id:
            event.message_obj.group_id = None  # type: ignore
            event.message_obj.sender.user_id = self.cfg.admin_id

        chain = []

        if message:
            chain.append(Plain(message))

        chain.append(await self._post_to_seg(post))

        await event.send(event.chain_result(chain))

    async def send_msg(
        self,
        event: AstrMessageEvent,
        message: str = "",
    ):
        seg = await self._text_to_seg(message)
        await self._send_chain(event, seg)
