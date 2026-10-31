# 更新日志

## v1.0.6

### 优化
- 代码清理

## v1.0.5

### 修复
- 点赞/取消点赞 API 返回 302 重定向导致解析失败；关闭 `aiohttp` 自动重定向 (`client.py`)
- QQ 空间下架 `liked` 字段，移除 `read_like_state()`/`like_count` 对比/`fast` 参数/`already_unliked` 等死代码
- `parse_recent_feeds` 用 `feed.pic` 作为头像 URL 错误；改为 `avatar_url=None`，前端通过 UIN 生成头像
- `parse_recent_feeds` 评论循环 `nickname` 变量覆盖发布者昵称；重命名为 `comment_nickname`
- `parse_recent_feeds` 昵称提取补充从 `name`/`userinfo`/`user`/`data` 嵌套及 HTML `a.f-name`/`span.f-name` 提取
- `page_feed` 始终返回 `pos=0` 导致"加载更多"重复；实现真正分页：接受 `cursor`，`get_recent_feeds` 传递 `begintime`，`parse_recent_feeds` 返回 `(posts, has_more, cursor)`，`query_feeds` 从最旧帖子时间计算下一次 cursor
- `query_feeds` 返回 `tuple[posts, has_more, cursor]`，更新所有调用者

### 优化
- WebUI 点赞按钮：👍图标+点赞数，无颜色切换；前端 `likeState` Map 跟踪 toggle
- 详情页点赞按钮显示👍图标+点赞数
- `_like_result_text` 简化，移除 `already_unliked` 分支
- `LikeResult` 移除 `already_unliked` 状态

## v1.0.4

### 修复
- `api.py` 缺少 `import re` 导致 `NameError`
- `LikeResult` 误放 `to_str`/`update` 方法，移回 `Post`
- `accepted_unverified` 返回 `verified=False`
- 移除 `abstime` 回退到当前时间
- `json5` 导入到模块级别

### 增强
- 点赞回读新增好友说说列表兼容回退
- 备用 key 兼容提交
- `like_context` SQLite 增量迁移

### 优化
- DEBUG 覆盖层优化

<details>
<summary>历史版本</summary>

## v1.0.3

### 修复
- `function object is not subscriptable` 加载错误

### 优化
- 重新分类配置项，旧版自动迁移

## v1.0.2

### 修复
- "仅通知管理员"模式仍发送到群聊
- 增加自动触发总开关
- 空间轮询再次校验开关
- 移除未实现定时功能
- 修复忽略群聊配置
- 轮询间隔限制为 10/12/15/20/30 分钟
- 扩展管理员私发结果
- 清理访客查询

## v1.0.1
- 声明最低 AstrBot 版本为 `4.24.2`
- 明确仪表盘依赖 AstrBot 原生 Plugin Pages

## v1.0.0
- 首个可用版本发布

鸣谢: [Zhalslar/astrbot_plugin_qzone](https://github.com/Zhalslar/astrbot_plugin_qzone)

</details>
