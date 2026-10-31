# QQ 空间多 Bot 管理 | Qzone Multibot Manager (AstrBot Plugin)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-4.24.2%2B-brightgreen)
![Version](https://img.shields.io/badge/Version-v1.0.2-blueviolet)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)

![views](https://count.getloli.com/@astrbot_plugin_qzone_multibots?name=astrbot_plugin_qzone_multibots&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

## ✨ 简介 | Introduction

<table>
  <tr>
    <td width="190" align="center">
      <img width="170" alt="QQ 空间插件 Logo" src="logo.png" style="border-radius: 24px;" />
    </td>
    <td>
      <strong>QQ 空间多 Bot 管理</strong><br />
      多 Bot 同时在线 · 独立空间账号 · 自动互动 · WebUI 统一管理<br />
      <sub>Manage multiple QQ Qzone accounts through separate AstrBot OneBot instances.</sub>
    </td>
  </tr>
</table>

**QQ 空间多 Bot 管理** 是一个 AstrBot QQ 空间多账号插件，通过多个 **aiocqhttp** 平台实例绑定多个 QQ 账号，实现多 Bot 同时在线并分别操作 QQ 空间；支持发布动态、轮询并评论好友动态、回复 Bot 自己动态下的新评论，以及通过 WebUI 统一管理；项目重构自 [原版 QQ 空间插件](https://github.com/Zhalslar/astrbot_plugin_qzone)

[![Release](https://img.shields.io/github/v/release/DearCrazyLeaf/astrbot_plugin_qzone_multibots?include_prereleases&color=blueviolet&label=最新版本)](https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/releases)
[![License](https://img.shields.io/badge/许可证-GPL--3.0-orange)](LICENSE)
[![Issues](https://img.shields.io/github/issues/DearCrazyLeaf/astrbot_plugin_qzone_multibots?color=darkgreen&label=反馈)](https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/DearCrazyLeaf/astrbot_plugin_qzone_multibots?color=blue&label=贡献)](https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/pulls)
[![QQ Group](https://img.shields.io/badge/点击加入QQ群-12B7F5?logo=tencentqq&logoColor=white&label=问题反馈和建议)](https://qm.qq.com/q/H3uUCEZKgg)
[![GitHub Stars](https://img.shields.io/github/stars/DearCrazyLeaf/astrbot_plugin_qzone_multibots?color=yellow&label=标星)](https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/stargazers)

> [!IMPORTANT]
> 本插件通过已连接的 aiocqhttp 平台实例获取登录信息和 Cookie，请先确保 OneBot 账号已成功连接，并已在 QQ 空间完成登录；不同平台实例分别对应各自的 QQ 空间账号

## ✨ 功能列表 | Features

- **多账号会话**：自动发现 AstrBot 中的多个 aiocqhttp 实例，并为每个实例维护独立的 QQ 空间会话和操作服务
- **查看说说**：查看自己或指定用户的空间动态、评论和详情，LLM 工具支持指定动态序号
- **发布与管理**：发布文字或带图说说，评论、回复评论、点赞和删除自己发布的说说
- **LLM 工具**：让模型根据对话内容撰写并发布说说，也可查询动态并按需点赞或评论
- **聊天触发互动**：按概率检查发言用户的最新说说并评论，可配置评论后点赞；可选择将实际评论结果私发给管理员
- **空间动态轮询**：按间隔检查各账号好友新动态并评论，也会检查 Bot 自己动态下的新评论并自动回复
- **自动触发总开关**：统一启停聊天概率互动与空间动态轮询；手动 LLM 工具和 WebUI 操作不受影响
- **WebUI 仪表盘**：在 AstrBot 仪表盘查看账号状态和动态，并执行发布、点赞、评论、回复、删除及图片上传
- **统一卡片渲染**：使用内置渲染器展示空间动态；卡片生成失败时回退为文本
- **任务提示词配置**：调整评论和评论回复的 LLM 附加指令
- **触发过滤**：配置忽略的群聊和用户，避免在指定来源触发聊天概率互动

## 🖼️ 效果展示 | Screenshots

<img width="600" style="max-width: 100%; max-height: 800px; object-fit: contain;" alt="多个 QQ 空间账号切换示例" src="docs/images/account_list.png" />

<img width="600" style="max-width: 100%; max-height: 800px; object-fit: contain;" alt="QQ 空间说说发布与互动效果" src="docs/images/qzone_test.jpg" />

<img width="600" style="max-width: 100%; max-height: 800px; object-fit: contain;" alt="QQ 空间 WebUI 仪表盘" src="docs/images/webui.png" />

## 📥 安装 | Installation

在 AstrBot 插件市场搜索 `astrbot_plugin_qzone_multibots` 并安装，或将仓库克隆到插件目录：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots
```

需要 AstrBot `4.24.2` 或更高版本（用于原生插件 WebUI 页面），重启 AstrBot 后，在 WebUI 的“QQ 空间多 Bot 管理”插件配置中设置本插件，插件依赖会按 `requirements.txt` 安装

## ⚙️ 配置 | Configuration

配置入口：

```text
AstrBot WebUI -> 插件 -> QQ 空间多 Bot 管理 -> 插件配置
```

---

### 核心配置

| 配置项 | 说明 |
|--------|------|
| `llm.comment_prompt` | 聊天触发、动态轮询和 LLM 工具评论好友动态时使用的附加指令 |
| `llm.reply_prompt` | 轮询回复 Bot 自己动态下新评论时使用的附加指令 |
| `source.ignore_groups` | 不在这些群聊触发聊天概率互动 |
| `source.ignore_users` | 不参与聊天概率互动的用户列表 |
| `trigger.auto_trigger_enabled` | 自动触发总开关，默认关闭；关闭时聊天概率互动和空间轮询均停止，手动工具和 WebUI 不受影响 |
| `trigger.read_prob` | 对话中随机触发评论的概率，默认 `0.001`；建议保持较低值 |
| `trigger.send_admin` | 是否将聊天触发和轮询的实际评论/回复及动态卡片私发给 AstrBot 首位管理员；发送失败时不会回落到触发会话 |
| `trigger.like_when_comment` | 评论说说后是否自动点赞，默认开启 |
| `connection.cookie_ttl` | Cookie 主动刷新的 TTL（秒），默认 `600`；设为 `0` 关闭 TTL 刷新 |
| `timeout` | QQ 空间请求超时秒数，默认 `10` |
| `polling.enabled` | 是否启用空间动态轮询，默认关闭 |
| `polling.interval` | 动态轮询间隔（分钟），可选 `10`、`12`、`15`、`20` 或 `30`，默认 `30` |
| `polling.batch_limit` | 每个 Bot 每轮新动态评论数和新评论回复数各自的上限，超出部分留待后续轮询，默认 `5` |
| `debug_mode` | 是否输出账号诊断、接口响应等详细调试日志；排障时开启 |

---

## 📖 使用说明 | Usage

插件将查询和发布操作注册为 LLM 工具，启用可用的 LLM 提供商后，用户可直接用自然语言请求机器人查看、发布或互动；工具会根据当前消息所属的平台实例选择对应 QQ 空间账号；支持的平台适配器为 **aiocqhttp / OneBot v11**

---

### LLM 工具

| 工具 | 功能 |
|------|------|
| `llm_view_feed` | 查看自己或指定 QQ 用户的说说，可选择点赞、评论或同时执行 |
| `llm_publish_feed` | 发布说说；默认尝试从当前对话获取图片 |
| `llm_qzone_status` | 逐个检查已挂载账号的 QQ 空间登录与 Cookie 状态 |

例如可以对机器人说：

```text
看看我最新的空间动态
看看 QQ 12345678 的第 2 条说说并点赞
把刚才讨论的活动写成一条简短说说发到空间
检查所有 QQ 空间账号是否已登录
```

实际是否调用工具由所选 LLM 和当前对话决定。涉及发布、评论、点赞或删除时，请确认对应平台账号及操作目标

---

### WebUI 仪表盘

打开 AstrBot 的 QQ 空间插件页面，可选择账号查看动态和状态，并在页面中查看说说详情、上传图片、发布说说、点赞、评论、回复评论或删除自己发布的内容。仪表盘操作会使用所选平台实例对应的 QQ 空间账号

---

### 自动互动

- **聊天随机互动**：仅在 `trigger.auto_trigger_enabled` 与 `trigger.read_prob` 均启用时检查发言用户的最新说说并评论；人格和 provider 来自触发消息的会话，可选自动点赞；开启 `send_admin` 后将实际评论及动态卡片私发给管理员，失败时不会回落到触发会话
- **动态轮询**：需同时开启 `trigger.auto_trigger_enabled` 和 `poll_enabled`；轮询间隔可设为 10、12、15、20 或 30 分钟，每个 Bot 每轮最多分别处理 `poll_batch_limit` 条新动态和新评论，好友动态读取最新 20 条，自己的动态也读取最新 20 条，各 Bot 按自己与管理员的私聊会话选择 provider 和人格；若该会话未设置人格，则使用对应平台默认人格；轮询没有聊天事件上下文，因此不会继承其他群聊里的临时人格，每个 Bot 只用自己的账号评论好友新动态、回复自己动态下的新评论；开启 `send_admin` 后，处理成功的实际评论/回复和动态卡片通过执行操作的 Bot 私发给管理员，首次轮询只建立基线，不处理已有动态和评论
- 插件当前不提供定时发说说或定时评论功能；说说发布可通过 LLM 工具或仪表盘手动发起

## 🛠️ 问题排查 | Troubleshooting

- 确认 AstrBot 中的 aiocqhttp 平台实例已连接，且实例名称（平台 ID）互不重复
- 若 QQ 空间操作提示未登录或 Cookie 失效，可调用 `llm_qzone_status` 检查账号状态，并确认对应 QQ 已登录空间
- 若卡片无法显示，插件会回退发送文本；可检查 AstrBot 控制台日志和网络资源访问情况
- 排查期间可开启 `debug_mode` 查看平台会话池、账号诊断和接口原始响应，问题解决后建议关闭

**如果有任何问题，请扫描下方二维码加入 QQ 群咨询👥**

<p align="center">
  <a href="https://qm.qq.com/q/H3uUCEZKgg" target="_blank">
    <img src="https://api.qrserver.com/v1/plugins/qrcode/v1.0/get?size=180x180&data=https%3A%2F%2Fqm.qq.com%2Fq%2FH3uUCEZKgg"
         alt="加入QQ群 👥" width="180" height="180"
         style="border-radius: 12px; border: 2px solid #007BFF; box-shadow: 0 4px 12px rgba(0, 123, 255, 0.2);">
  </a>
</p>

<p align="center" style="font-size: 13px; color: #666; margin-top: 8px;">
  <a href="https://qm.qq.com/q/H3uUCEZKgg" target="_blank">扫描二维码加入 QQ 群</a> · <a href="https://qm.qq.com/q/H3uUCEZKgg" target="_blank">Scan to Join QQ Group</a>
</p>

## ❤️ 贡献者 | Contributors

<a href="https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=DearCrazyLeaf/astrbot_plugin_qzone_multibots&max=300&columns=15" alt="Contributors" />
</a>

## 🤝 致谢 | Acknowledgements

- 作者：[DearCrazyLeaf](https://github.com/DearCrazyLeaf)
- 感谢 [Zhalslar](https://github.com/Zhalslar) 的原版 QQ 空间插件及项目贡献者
- 部分思路参考 [CampuxBot](https://github.com/idoknow/CampuxBot) 与 QQ 空间相关开源项目
- 点赞部分思路参考 [diaomin66](https://github.com/diaomin66) 的 Ultra 版本

## 📜 许可证 | License

[![GPL-3.0 License](https://img.shields.io/badge/License-GPL--3.0-orange?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0.txt)

---

> Made for AstrBot ❤️
