from astrbot.core.message.components import Image, Reply
from astrbot.core.platform import AstrMessageEvent


async def get_image_urls(event: AstrMessageEvent, reply: bool = True) -> list[str]:
    """获取当前消息及可选引用消息中的图片地址。"""
    chain = event.get_messages()
    images: list[str] = []
    if reply:
        reply_seg = next((seg for seg in chain if isinstance(seg, Reply)), None)
        if reply_seg and reply_seg.chain:
            images.extend(
                seg.url
                for seg in reply_seg.chain
                if isinstance(seg, Image) and seg.url
            )
    images.extend(
        seg.url for seg in chain if isinstance(seg, Image) and seg.url
    )
    return images
