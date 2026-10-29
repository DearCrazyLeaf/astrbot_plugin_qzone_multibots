"""空间动态轮询器。"""
import re
from typing import Any

from astrbot.api import logger


class QzonePoller:
    def __init__(self, plugin):
        self.plugin = plugin
        self._baseline_ready: set[str] = set()

    async def poll(self):
        self.plugin._ensure_accounts()
        for account, service in list(self.plugin.services.items()):
            try:
                uin = int(await self.plugin.sessions[account].get_uin())
                posts = await service.query_feeds(pos=0, num=20)
                if account not in self._baseline_ready:
                    for post in posts:
                        await self.plugin.db.mark_snapshot(uin, post.tid)
                    self._baseline_ready.add(account)
                    logger.info(f"Poller[{uin}] 首轮基线已记录 {len(posts)} 条动态")
                    continue
                fresh = []
                for post in posts:
                    if not post.tid:
                        continue
                    if not await self.plugin.db.has_snapshot(uin, post.tid):
                        fresh.append(post)
                for post in fresh[:max(1, int(self.plugin.cfg.poll_batch_limit))]:
                    # 先点赞；LLM 失败时保留快照，防止下一轮重复动作。
                    await service.like_posts(post)
                    await self.plugin.db.mark_snapshot(uin, post.tid)
                    try:
                        # LLMAction 有 generate_comment 复用入口，但它绑定插件自选 provider 配置；
                        # 此处按要求使用当前会话框架 provider，并保留会话 UMO 上下文。
                        content = await self._generate_comment(post, account)
                        if content:
                            await service.qzone.comment(post, content)
                        else:
                            logger.warning(f"Poller[{uin}] 评论生成为空，仅点赞")
                    except Exception as exc:
                        logger.warning(f"Poller[{uin}] 评论生成失败，仅点赞：{exc}")
            except Exception as exc:
                logger.warning(f"Poller[{account}] 轮询失败：{exc}")

    async def _generate_comment(self, post, account: str) -> str:
        context = self.plugin.context
        provider = context.get_using_provider()
        if provider is None:
            raise RuntimeError("当前未配置可用模型提供商")
        system_prompt, contexts = await self.plugin.llm._build_request_context(
            event=None, task_prompt="根据说说内容写一句自然、简短的评论，只输出评论。"
        )
        # 当前无消息事件，使用框架当前 provider 链路；会话历史无法绑定具体 UMO。
        response = await provider.text_chat(
            system_prompt=system_prompt,
            prompt=f"说说：{post.text or post.rt_con}",
            contexts=contexts,
        )
        return re.sub(r"[\s\u3000]+", "", response.completion_text).strip("。")

    async def register(self):
        # AstrBot 标准 cron 入口：context.cron_manager（CronJobManager）。
        # persistent=False，重启后由插件 initialize 重新注册，不在数据库残留。
        manager = getattr(self.plugin.context, "cron_manager", None)
        if manager is None:
            logger.error("Poller 无法注册：当前 AstrBot Context 未暴露 cron_manager")
            return
        interval = max(10, int(self.plugin.cfg.poll_interval))
        # cron 步进 */m 只支持 m<=59，超限时回落到 59
        step = min(interval, 59)
        job = await manager.add_basic_job(
            name=f"qzone_poller_{id(self)}",
            cron_expression=f"*/{step} * * * *",
            handler=self.poll,
            description="qzone 插件空间动态轮询",
            persistent=False,
        )
        self._job_id = job.job_id
        logger.info(f"Poller 已注册，间隔约 {interval} 分钟（cron */{step}）")

    async def unregister(self):
        job_id = getattr(self, "_job_id", None)
        if job_id is not None:
            try:
                manager = getattr(self.plugin.context, "cron_manager", None)
                if manager is not None:
                    await manager.delete_job(job_id)
            except Exception as exc:
                logger.warning(f"Poller 注销失败：{exc}")
            self._job_id = None

    async def close(self):
        await self.unregister()
        self._baseline_ready.clear()

# PostDB snapshot methods are implemented in core.db.
