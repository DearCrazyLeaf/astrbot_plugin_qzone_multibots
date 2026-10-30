from astrbot.api import logger
from astrbot.core.message.components import BaseMessageComponent, Image, Plain
from astrbot.core.message.message_event_result import MessageChain
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

    async def _send_to_admin(
        self,
        event: AstrMessageEvent,
        chain: list[BaseMessageComponent],
    ) -> bool:
        admin_id = str(self.cfg.admin_id or "").strip()
        if not admin_id.isdigit():
            logger.warning("管理员私发失败：AstrBot 未配置有效的管理员 QQ 号")
            return False

        try:
            platform_id = str(event.get_platform_id() or "").strip()
        except Exception as exc:
            logger.warning("管理员私发失败：无法获取当前平台实例 ID：%s", exc)
            return False
        if not platform_id:
            logger.warning("管理员私发失败：无法获取当前平台实例 ID")
            return False

        return await self._send_to_admin_platform(
            platform_id,
            MessageChain(chain=chain),
        )

    async def _send_to_admin_platform(
        self,
        platform_id: str,
        message_chain: MessageChain,
    ) -> bool:
        admin_id = str(self.cfg.admin_id or "").strip()
        if not admin_id.isdigit():
            logger.warning("管理员私发失败：AstrBot 未配置有效的管理员 QQ 号")
            return False
        if not platform_id:
            logger.warning("管理员私发失败：无法获取当前平台实例 ID")
            return False

        umo = f"{platform_id}:FriendMessage:{admin_id}"
        try:
            sent = await self.cfg.context.send_message(
                session=umo,
                message_chain=message_chain,
            )
            if sent is True:
                return True
            logger.warning("管理员私发失败：AstrBot 未找到可用的平台实例")
        except Exception as exc:
            logger.warning("管理员私发失败：%s", exc)
        return False

    async def send_admin_result(
        self,
        platform_id: str,
        post: Post,
        message: str,
    ) -> bool:
        chain = [Plain(message), await self._post_to_seg(post)]
        return await self._send_to_admin_platform(
            platform_id,
            MessageChain(chain=chain),
        )

    async def send_post(
        self,
        event: AstrMessageEvent,
        post: Post,
        *,
        message: str = "",
        send_admin: bool = False,
    ):
        chain = []

        if message:
            chain.append(Plain(message))

        chain.append(await self._post_to_seg(post))

        if send_admin:
            admin_id = str(self.cfg.admin_id or "").strip()
            if not admin_id.isdigit():
                logger.warning("管理员 QQ 号未配置，自动触发结果静默处理")
                return
            if not await self._send_to_admin(event, chain):
                logger.warning("管理员私发失败，自动触发结果静默处理")
                return
            return

        await event.send(event.chain_result(chain))
