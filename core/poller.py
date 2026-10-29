"""空间动态和评论轮询器。"""

from astrbot.api import logger


class QzonePoller:
    def __init__(self, plugin):
        self.plugin = plugin
        self._baseline_ready: set[str] = set()

    def _account_umo(self, account: str, uin: int) -> str:
        # 每个 aiocqhttp 实例有独立的 UMO；使用管理员私聊会话读取该 Bot
        # 对应会话/provider/persona 设置，不借用进程级“当前 provider”。
        user_id = str(self.plugin.cfg.admin_id or uin)
        return f"{account}:FriendMessage:{user_id}"

    async def _baseline_comments(self, account_uin: int, posts) -> None:
        snapshots = []
        for post in posts:
            if not post.tid:
                continue
            for comment in post.comments:
                if comment.tid:
                    snapshots.append((post.tid, str(comment.tid)))
        await self.plugin.db.mark_comment_snapshots(account_uin, snapshots)

    async def _notify_admin(self, account: str, post, action: str, content: str):
        if not self.plugin.cfg.trigger.send_admin:
            return
        await self.plugin.sender.send_admin_result(
            account,
            post,
            f"[{account}] 轮询{action}成功\n实际内容：{content}",
        )

    async def poll(self):
        if (
            not self.plugin.cfg.trigger.auto_enabled
            or not self.plugin.cfg.polling.enabled
        ):
            return

        self.plugin._ensure_accounts()
        for account, service in list(self.plugin.services.items()):
            try:
                uin = int(await self.plugin.sessions[account].get_uin())
                umo = self._account_umo(account, uin)
                feed_posts = await service.query_feeds(
                    pos=0, num=20, no_self=True
                )
                own_posts = await service.query_feeds(
                    target_id=str(uin), pos=0, num=20
                )

                if account not in self._baseline_ready:
                    for post in feed_posts:
                        await self.plugin.db.mark_snapshot(uin, post.tid)
                    await self._baseline_comments(uin, own_posts)
                    self._baseline_ready.add(account)
                    logger.info(
                        f"Poller[{uin}] 首轮基线已记录 {len(feed_posts)} 条动态及自己动态的评论"
                    )
                    continue

                limit = max(1, int(self.plugin.cfg.polling.batch_limit))
                handled_posts = 0

                # 好友新动态：由当前账号对应的 provider/persona 生成评论，再由该账号操作。
                for post in feed_posts:
                    if handled_posts >= limit:
                        break
                    if not post.tid or await self.plugin.db.has_snapshot(uin, post.tid):
                        continue
                    handled_posts += 1
                    try:
                        content = await service.comment_posts(post, umo=umo)
                        await self.plugin.db.mark_snapshot(uin, post.tid)
                        if self.plugin.cfg.trigger.like_when_comment:
                            try:
                                await service.like_posts(post)
                            except Exception as exc:
                                logger.warning(f"Poller[{uin}] 点赞失败：{exc}")
                        await self._notify_admin(account, post, "评论", content)
                    except Exception as exc:
                        logger.warning(f"Poller[{uin}] 新动态处理失败：{exc}")

                # 自己动态下的新评论：忽略本账号自己的评论，防止回复自身造成循环。
                handled_comments = 0
                own_post_tids = [str(post.tid) for post in own_posts if post.tid]
                seen_comments = await self.plugin.db.get_comment_snapshots(
                    uin, own_post_tids
                )
                new_comments = []
                own_comment_snapshots = []
                for post in own_posts:
                    if not post.tid:
                        continue
                    for comment in post.comments:
                        if not comment.tid:
                            continue
                        snapshot = (str(post.tid), str(comment.tid))
                        if snapshot in seen_comments:
                            continue
                        if comment.uin != uin and handled_comments >= limit:
                            continue
                        seen_comments.add(snapshot)
                        if comment.uin == uin:
                            own_comment_snapshots.append(snapshot)
                            continue
                        handled_comments += 1
                        new_comments.append((post, comment))

                await self.plugin.db.mark_comment_snapshots(uin, own_comment_snapshots)
                for post, comment in new_comments:
                    try:
                        content = await service.reply_to_comment(
                            post, comment, umo=umo
                        )
                        await self.plugin.db.mark_comment_snapshots(
                            uin, [(str(post.tid), str(comment.tid))]
                        )
                        await self._notify_admin(account, post, "回复评论", content)
                    except Exception as exc:
                        logger.warning(f"Poller[{uin}] 回复新评论失败：{exc}")
            except Exception as exc:
                logger.warning(f"Poller[{account}] 轮询失败：{exc}")

    async def register(self):
        manager = getattr(self.plugin.context, "cron_manager", None)
        if manager is None:
            logger.error("Poller 无法注册：当前 AstrBot Context 未暴露 cron_manager")
            return
        valid_intervals = (10, 12, 15, 20, 30)
        configured_interval = int(self.plugin.cfg.polling.interval)
        interval = configured_interval if configured_interval in valid_intervals else 30
        if interval != configured_interval:
            logger.warning(
                f"不支持的轮询间隔 {configured_interval} 分钟，已回退为 {interval} 分钟"
            )
        job = await manager.add_basic_job(
            name=f"qzone_poller_{id(self)}",
            cron_expression=f"*/{interval} * * * *",
            handler=self.poll,
            description="qzone 插件空间动态及评论轮询",
            persistent=False,
        )
        self._job_id = job.job_id
        logger.info(f"Poller 已注册，间隔约 {interval} 分钟（cron */{interval}）")

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
