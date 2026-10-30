# 更新日志

本文档记录 `astrbot_plugin_qzone_multibots` 的版本变更

## v1.0.4

### 修复
- 修复 `api.py` 缺少 `import re` 导致 HTML 响应回退解析路径崩溃的 `NameError`
- 将误放置在 `LikeResult`（frozen dataclass）上的 `to_str` 与 `update` 方法移回 `Post`，修复 `sender.py` 调用 `post.to_str()` 时的 `AttributeError` 及 `LikeResult` 无法更新属性的问题
- 修正 `accepted_unverified` 状态返回 `verified=False`（而非 `True`），防止未验证状态被误报为已验证
- 移除 `abstime` 回退到当前时间的逻辑，符合方案约定：发布时间无法确认时保留为 `0`
- 移动 `json5` 导入到模块级别，消除运行时内联导入
- WebUI `toggleLike` 状态检查改为匹配 `accepted_unverified` 而非 Ultra 的 `accepted_pending_verification`

### 增强
- 点赞状态回读新增好友说说列表兼容回退，提高状态确认率
- 实现备用 key 兼容提交：当主 key 来自 QQ 真实返回且状态未验证时，尝试一次 Ultra 格式备用 key
- 新增 `like_context` SQLite 增量迁移，持久化 `appid/curkey/unikey/like_abstime/liked/like_count`，避免重启后丢失

### 优化
- 优化 `DEBUG` 覆盖层，添加更全面的排障信息

## v1.0.3

### 修复
- 修复 `function object is not subscriptable` 加载错误

### 优化
- 优化配置项，重新按照各项功能分类
- 旧版平铺配置自动迁移到新分组，并保留原有设置值

## v1.0.2

### 修复
- 修复“仅通知管理员”模式只修改事件字段却仍发送到触发会话的问题，改用当前 aiocqhttp 平台实例向管理员私聊发送；私发失败时不回落到群聊，避免意外泄露
- 新增默认关闭的自动触发总开关，统一控制聊天概率互动和空间动态轮询；手动 LLM 工具与 WebUI 操作不受影响
- 空间轮询执行时再次校验总开关和轮询子开关，避免已注册任务在功能关闭后继续执行
- 移除尚未实现的定时发说说/定时评论配置和未使用的说说生成设置，避免误导用户
- 让忽略群聊配置生效，并让评论后点赞设置同时控制聊天触发与动态轮询
- 将轮询间隔限制为 10、12、15、20 或 30 分钟，并在旧配置值不符合选项时回退到 30 分钟
- 轮询按各 aiocqhttp 实例的会话 provider/人格生成评论或回复；为每个账号独立处理好友新动态及 Bot 自己动态下的新评论
- 扩展管理员私发结果，成功时附带实际生成的评论/回复文本；轮询复用该通知开关并通过执行操作的 Bot 账号私发
- 清理未接入的访客查询和旧版辅助方法，修正文档与配置提示中的失效描述

<details>
<summary>历史版本（点击展开）</summary>

## v1.0.1

### 修复
- 声明最低 AstrBot 版本为 `4.24.2`，该版本开始支持插件自定义 WebUI 页面
- 明确仪表盘依赖 AstrBot 原生 Plugin Pages 页面发现和鉴权机制，不添加绕过该机制的静态路由
- 修复仪表盘 API 仍使用原版插件名路径的问题，使前端请求与 `astrbot_plugin_qzone_multibots` 的插件路由匹配

## v1.0.0

### 新增
- 首个可用版本发布

### 鸣谢
- [原版 QQ 空间插件](https://github.com/Zhalslar/astrbot_plugin_qzone)
- [Zhalslar](https://github.com/Zhalslar) 原版 `QQ空间插件` 作者

</details>
