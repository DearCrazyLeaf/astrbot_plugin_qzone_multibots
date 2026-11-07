import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import pydantic
from pydantic import BaseModel

VideoAnalysisStatus = Literal[
    "not_requested",
    "unavailable",
    "not_configured",
    "provider_unavailable",
    "succeeded",
    "partial",
    "failed",
]


def extract_and_replace_nickname(input_string):
    # 匹配{}内的内容，包括非标准JSON格式
    pattern = r"\{[^{}]*\}"

    def replace_func(match):
        content = match.group(0)
        # 按照键值对分割
        pairs = content[1:-1].split(",")
        nick_value = ""
        for pair in pairs:
            if ":" not in pair:
                continue
            key, value = pair.split(":", 1)
            if key.strip() == "nick":
                nick_value = value.strip()
                break
        # 如果找到nick值，则返回@nick_value，否则返回空字符串
        return f"{nick_value} " if nick_value else ""

    return re.sub(pattern, replace_func, input_string)


def remove_em_tags(text):
    """
    移除字符串中的 [em]...[/em] 标记
    :param text: 输入的字符串
    :return: 移除标记后的字符串
    """
    # 使用正则表达式匹配 [em]...[/em] 并替换为空字符串
    cleaned_text = re.sub(r"\[em\].*?\[/em\]", "", text)
    return cleaned_text


class Comment(BaseModel):
    """QQ 空间单条评论（含主评论与楼中楼）"""

    uin: int
    nickname: str
    content: str
    create_time: int
    create_time_str: str = ""
    tid: int = 0
    parent_tid: int | None = None  # 为 None 表示主评论
    source_name: str = ""
    source_url: str = ""

    # 可选：去掉 QQ 内置表情标记 [em]e123[/em]
    @property
    def plain_content(self) -> str:
        return re.sub(r"\[em\]e\d+\[/em\]", "", self.content)

    # ------------------- 工厂方法 -------------------
    @staticmethod
    def from_raw(raw: dict, parent_tid: int | None = None) -> "Comment":  # noqa: UP037
        """单条 dict → Comment（内部使用）"""
        return Comment(
            uin=int(raw.get("uin") or 0),
            nickname=raw.get("name") or "",
            content=raw.get("content") or "",
            create_time=int(raw.get("create_time") or 0),
            create_time_str=raw.get("createTime2") or "",
            tid=int(raw.get("tid") or 0),
            parent_tid=parent_tid,
            source_name=raw.get("source_name") or "",
            source_url=raw.get("source_url") or "",
        )

    @staticmethod
    def build_list(comment_list: list[dict]) -> list["Comment"]:  # noqa: UP037
        """把 emotion_cgi_msgdetail_v6 里的 commentlist 整段 flatten 成 List[Comment]"""
        res: list["Comment"] = []  # noqa: UP037
        for main in comment_list:
            # 主评论
            main_tid = int(main.get("tid") or 0)
            res.append(Comment.from_raw(main, parent_tid=None))
            # 楼中楼
            for sub in main.get("list_3") or []:
                res.append(Comment.from_raw(sub, parent_tid=main_tid))
        return res

    # ------------------- 方便打印 / debug -------------------
    def __str__(self) -> str:
        flag = "└─↩" if self.parent_tid else "●"
        return f"{flag} {self.nickname}({self.uin}): {self.plain_content}"


class Post(pydantic.BaseModel):
    """稿件"""

    id: int | None = None
    """稿件ID"""
    tid: str | None = None
    """QQ给定的说说ID"""
    uin: int = 0
    """用户ID"""
    name: str = ""
    """用户昵称"""
    avatar_url: str | None = None
    """用户头像地址"""
    gin: int = 0
    """群聊ID"""
    text: str = ""
    """文本内容"""
    images: list[str] = pydantic.Field(default_factory=list)
    """图片列表"""
    videos: list[str] = pydantic.Field(default_factory=list)
    """视频列表"""
    has_video: bool = False
    """接口明确标识视频，但不保证存在播放地址"""
    video_analysis: str = ""
    """本次请求的视频识别结果，不写入数据库"""
    video_analysis_status: VideoAnalysisStatus = "not_requested"
    """本次请求的视频识别状态"""
    anon: bool = False
    """是否匿名"""
    status: str = "approved"
    """状态"""
    create_time: int = pydantic.Field(
        default_factory=lambda: int(datetime.now().timestamp())
    )
    """创建时间"""
    rt_con: str = ""
    """转发内容"""
    comments: list[Comment] = pydantic.Field(default_factory=list)
    """评论列表"""
    extra_text: str | None = None
    """额外文本"""
    appid: int = 311
    """QQ 空间动态应用 ID"""
    like_typeid: int = 0
    """QQ 空间点赞接口类型 ID"""
    curkey: str = ""
    """QQ 空间返回的动态操作 key"""
    unikey: str = ""
    """QQ 空间返回的动态唯一 key"""
    like_abstime: int = 0
    """QQ 空间动态的服务端发布时间"""
    liked: bool | None = None
    """当前会话账号对该动态的点赞状态，None 表示未知"""
    like_count: int = 0
    """QQ 空间返回的动态点赞数"""
    like_request_pending: bool | None = None
    """本进程已提交但尚未回读确认的点赞目标状态"""
    self_commented: bool | None = None
    """当前会话账号是否已评论该动态，None 表示未知"""
    comments_checked: bool = False
    """是否已通过详情接口检查评论列表"""

    @property
    def like_status_text(self) -> str:
        if self.liked is True:
            return "已点赞"
        if self.liked is False:
            return "未点赞"
        return "未知"

    @property
    def self_comment_status_text(self) -> str:
        if self.self_commented is True:
            return "已评论"
        if self.self_commented is False:
            return "未评论"
        return "未知"

    @property
    def video_analysis_status_text(self) -> str:
        if not (self.has_video or self.videos):
            return "不适用"
        return {
            "not_requested": "尚未请求识别",
            "unavailable": "视频播放地址不可用",
            "not_configured": "未配置识别模型",
            "provider_unavailable": "识别模型不可用",
            "succeeded": "识别完成",
            "partial": "部分视频识别失败或未处理",
            "failed": "识别失败",
        }[self.video_analysis_status]

    @property
    def video_status_text(self) -> str:
        return "包含视频" if self.has_video or self.videos else "非视频"

    class Config:
        json_encoders = {Comment: lambda c: c.model_dump()}

    def to_str(self) -> str:
        """把稿件信息整理成易读文本"""
        lines = [
            f"### 【{self.id}】{self.name}发布于{datetime.fromtimestamp(self.create_time).strftime('%Y-%m-%d %H:%M')}",
            f"本账号点赞状态（查询时）：{self.like_status_text}",
            f"本账号评论状态（查询时）：{self.self_comment_status_text}",
            f"动态视频状态（查询时）：{self.video_status_text}",
            f"视频识别状态（本次查询）：{self.video_analysis_status_text}",
        ]
        if self.text:
            lines.append(f"\n\n{remove_em_tags(self.text)}\n\n")
        if self.rt_con:
            lines.append(f"\n\n[转发]：{remove_em_tags(self.rt_con)}\n\n")
        if self.images:
            images_str = "\n".join(f"  ![图片]({img})" for img in self.images)
            lines.append(images_str)
        if self.videos:
            videos_str = "\n".join(f"  [视频]({vid})" for vid in self.videos)
            lines.append(videos_str)
        elif self.has_video:
            lines.append("视频：接口未提供播放地址")
        if self.video_analysis:
            lines.append(f"\n视频识别：{self.video_analysis}")
        if self.comments:
            lines.append("\n\n【评论区】\n")
            for comment in self.comments:
                comment_ref = (
                    f"（comment_id: {comment.tid}）"
                    if comment.tid
                    else "（评论 ID 不可用，无法指定回复）"
                )
                lines.append(
                    f"- **{remove_em_tags(comment.nickname)}**{comment_ref}: "
                    f"{remove_em_tags(extract_and_replace_nickname(comment.content))}"
                )
        return "\n".join(lines)

    def update(self, **kwargs):
        """更新 Post 对象的属性"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise AttributeError(f"Post 对象没有属性 {key}")


@dataclass(slots=True, frozen=True)
class LikeResult:
    """点赞请求和状态回读的结构化结果。"""

    status: Literal[
        "already_liked",
        "already_unliked",
        "skipped_unknown",
        "accepted_verified",
        "accepted_unverified",
        "pending_verification",
        "rejected",
    ]
    liked: bool | None
    verified: bool
    already: bool = False
    message: str = ""
