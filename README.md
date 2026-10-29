# QQ空间 Multibot | Qzone Multibot Manager (AstrBot Plugin)

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Version](https://img.shields.io/badge/Version-v1.0.0-blueviolet)
![License](https://img.shields.io/badge/License-GPL--3.0-orange)

![views](https://count.getloli.com/@astrbot_plugin_qzone_multibots?name=astrbot_plugin_qzone_multibots&theme=minecraft&padding=6&offset=0&align=top&scale=1&pixelated=1&darkmode=auto)

## ✨ 简介 | Introduction

<table>
  <tr>
    <td width="190" align="center">
      <img width="170" alt="QQ 空间插件 Logo" src="logo.png" style="border-radius: 24px;" />
    </td>
    <td>
      <strong>QQ空间 Multibot</strong><br />
      多 Bot 同时在线 · 独立空间账号 · 自动互动 · WebUI 统一管理<br />
      <sub>Manage multiple QQ Qzone accounts through separate AstrBot OneBot instances.</sub>
    </td>
  </tr>
</table>

**QQ空间 Multibot** 是一个 AstrBot QQ 空间多 Bot 账号管理插件，通过多个 **aiocqhttp** 平台实例绑定多个 QQ 账号，实现多 Bot 同时在线并分别操作 QQ 空间；支持自主发说说、轮询空间并评论、点赞、回复，以及通过 WebUI 统一管理；项目重构自 [原版 QQ 空间插件](https://github.com/Zhalslar/astrbot_plugin_qzone)

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
- **查看说说**：查看自己或指定用户的空间动态、评论和详情，支持按序号及范围查看
- **发布与管理**：发布文字或带图说说，评论、回复评论、点赞和删除自己发布的说说
- **LLM 工具**：让模型根据对话内容撰写并发布说说，也可查询动态并按需点赞或评论
- **自动发布**：从群聊记录中提取话题，按配置的 Cron 基准时间自动生成并发布说说
- **自动评论**：定时评论好友近期发布的说说；也可在聊天过程中以低概率触发评论，并可配置评论后点赞
- **动态轮询**：按间隔检查新增动态并自动互动，支持设置单次处理数量
- **WebUI 仪表盘**：在 AstrBot 仪表盘查看账号状态和动态，并执行发布、点赞、评论、回复、删除及图片上传
- **统一卡片渲染**：使用内置渲染器展示空间动态；卡片生成失败时回退为文本
- **任务提示词配置**：分别调整自动发说说、自动评论和评论回复的 LLM 附加指令
- **隐私过滤**：配置忽略的群聊和用户，避免从指定来源抽取聊天内容或触发随机互动

## 📥 安装 | Installation

在 AstrBot 插件市场搜索 `astrbot_plugin_qzone_multibots` 并安装，或将仓库克隆到插件目录：

```bash
cd /AstrBot/data/plugins
git clone https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots
```

重启 AstrBot 后，在 WebUI 的“QQ空间Multibot”插件配置中设置本插件，插件依赖会按 `requirements.txt` 安装

## ⚙️ 配置 | Configuration

配置入口：

```text
AstrBot WebUI -> 插件 -> QQ空间Multibot -> 插件配置
```

---

### 核心配置

| 配置项 | 说明 |
|--------|------|
| `llm.post_prompt` | 自动发说说时附加在人设后的任务指令 |
| `llm.comment_prompt` | 自动评论好友说说时附加的任务指令 |
| `llm.reply_prompt` | 回复他人评论时附加的任务指令 |
| `source.ignore_groups` | 不从这些群聊抽取聊天记录用于生成说说 |
| `source.ignore_users` | 忽略的用户列表；未开放空间的用户也可能被自动加入 |
| `source.post_max_msg` | 生成说说时读取的聊天记录最大条数，默认 `500` |
| `trigger.publish_cron` | 自动发说说的 Cron 基准时间；留空可禁用，默认每天 `23:30` |
| `trigger.publish_offset` | 发布任务相对 Cron 基准时间随机浮动的秒数，默认 `600` |
| `trigger.comment_cron` | 自动评论的 Cron 基准时间；留空可禁用，默认每天 `08:00` |
| `trigger.comment_offset` | 评论任务相对 Cron 基准时间随机浮动的秒数，默认 `600` |
| `trigger.read_prob` | 对话中随机触发评论的概率，默认 `0.001`；建议保持较低值 |
| `trigger.send_admin` | 是否将随机触发生成的互动结果仅发送给管理员审核 |
| `trigger.like_when_comment` | 评论说说后是否自动点赞，默认开启 |
| `cookie_ttl` | Cookie 主动刷新的 TTL（秒），默认 `600`；设为 `0` 关闭 TTL 刷新 |
| `timeout` | QQ 空间请求超时秒数，默认 `10` |
| `poll_enabled` | 是否启用空间动态轮询，默认关闭 |
| `poll_interval` | 动态轮询间隔（分钟），最小 `10`，默认 `30` |
| `poll_batch_limit` | 单次轮询处理上限，超出部分留待后续轮询，默认 `5` |
| `debug_mode` | 是否输出账号诊断、接口响应等详细调试日志；排障时开启 |

---

### 定时任务说明

- `publish_cron` / `comment_cron` 使用 Cron 表达式，字段顺序为“分 时 日 月 周”
- `publish_offset` / `comment_offset` 是基准时间前后的随机浮动范围，单位为秒
- 例如 `publish_cron = 30 23 * * *`、`publish_offset = 600` 表示每天约在 `22:50` 至 `23:50` 之间执行一次
- 将偏移设为 `0` 可严格按 Cron 时间触发；将 Cron 留空可禁用对应定时任务

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

- **定时发说说**：根据最近群聊记录生成文本，再通过当前可用账号发布；可用 `source.ignore_groups` 排除敏感群聊
- **定时评论**：在配置时段内浏览好友近期动态，过滤自己的说说及已评论内容后生成评论
- **聊天随机互动**：以 `trigger.read_prob` 配置的低概率检查发言用户的最新说说并评论；可选自动点赞，也可通过 `send_admin` 先发给管理员
- **动态轮询**：开启 `poll_enabled` 后周期性处理新动态；轮询间隔至少为 10 分钟，每轮最多处理 `poll_batch_limit` 条

## 🛠️ 问题排查 | Troubleshooting

- 确认 AstrBot 中的 aiocqhttp 平台实例已连接，且实例名称（平台 ID）互不重复
- 若 QQ 空间操作提示未登录或 Cookie 失效，可调用 `llm_qzone_status` 检查账号状态，并确认对应 QQ 已登录空间
- 若卡片无法显示，插件会回退发送文本；可检查 AstrBot 控制台日志和网络资源访问情况
- 排查期间可开启 `debug_mode` 查看平台会话池、账号诊断和接口原始响应，问题解决后建议关闭

## ❤️ 贡献者 | Contributors

<a href="https://github.com/DearCrazyLeaf/astrbot_plugin_qzone_multibots/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=DearCrazyLeaf/astrbot_plugin_qzone_multibots&max=300&columns=15" alt="Contributors" />
</a>

## 🤝 致谢 | Acknowledgements

- 作者：[DearCrazyLeaf](https://github.com/DearCrazyLeaf)
- 感谢 [Zhalslar](https://github.com/Zhalslar) 的原版 QQ 空间插件及项目贡献者
- 部分思路参考 [CampuxBot](https://github.com/idoknow/CampuxBot) 与 QQ 空间相关开源项目

## 📜 许可证 | License

[![GPL-3.0 License](https://img.shields.io/badge/License-GPL--3.0-orange?style=for-the-badge)](https://www.gnu.org/licenses/gpl-3.0.txt)

---

> Made for AstrBot ❤️
