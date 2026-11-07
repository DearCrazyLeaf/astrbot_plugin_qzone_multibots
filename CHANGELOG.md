# 更新日志

## v1.1.0

### 修复
- 修复WEBUI DashBoard无法正常显示账号是否点赞的问题
- 修复查询过滤器会漏掉广告的问题

### 优化
- 加强点赞检测逻辑，现在LLM工具/自动轮询会按照状态输出结果
- LLM 查询工具改为只读并返回动态引用；独立互动工具统一执行点赞、取消点赞、评论、回复及按需视频识别
- 查询结果明确展示本账号评论状态和视频识别状态；点赞请求未验证期间阻止同一动态的重复操作
- 视频识别超时日志区分下载、FFmpeg 准备/抽帧和识图模型调用阶段，并输出截断后的 FFmpeg 错误详情
- 配置识图模型后在插件启动时预检 FFmpeg；缺失时自动安装，失败则抛出带手动安装指引的启动异常
- 视频下载超时新增可配置项（10–300 秒，默认 30 秒）；识别和安装临时文件自动清理，FFmpeg 检查时清理旧版本运行时

## v1.0.9

### 修复
- 修复 LLM 指定用户查询仅读取普通说说接口，遗漏好友动态流中相册视频的问题；补充抓取目标作者的相册动态并与普通说说按时间合并
- 在统一动态查询中跳过明确的广告与游戏推广内容，防止 WebUI、LLM 工具和自动轮询对其互动

### 优化
- 强化多类型动态互动，按照说说类型适配 `点赞`/`取消点赞`、`评论`/`回复` 构造请求

## v1.0.8

### 修复
- 修复无法解析视频说说/相册的问题
- 修复LLM工具主动查询时无法解析视频说说/相册的问题
- 修复插件处理点赞/取消点赞时QQ空间受理但不记录的问题

### 新增
- 添加动态视频解析功能，通过截取视频帧使用可配置的识图模型进行视频总结，未配置模型时不会解析视频信息
- 可配置的视频识图模型

### 优化
- 重构WEBUI DashBoard页面

## v1.0.7

### 修复
- 修复转发卡片内容提取问题，避免遗漏转发的卡片信息

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

<details>
<summary>历史版本</summary>

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
