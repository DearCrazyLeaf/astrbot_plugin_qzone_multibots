# config.py
from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from astrbot.api import logger
from astrbot.core.config.astrbot_config import AstrBotConfig
from astrbot.core.star.context import Context
from astrbot.core.utils.astrbot_path import (
    get_astrbot_plugin_data_path,
    get_astrbot_temp_path,
)


class ConfigNode:
    """
    配置节点, 把 dict 变成强类型对象。

    规则：
    - schema 来自子类类型注解
    - 声明字段：读写，写回底层 dict
    - 未声明字段和下划线字段：仅挂载属性，不写回
    - 支持 ConfigNode 多层嵌套（lazy + cache）
    """

    _SCHEMA_CACHE: dict[type, dict[str, type]] = {}
    _FIELDS_CACHE: dict[type, set[str]] = {}

    @classmethod
    def _schema(cls) -> dict[str, type]:
        return cls._SCHEMA_CACHE.setdefault(cls, get_type_hints(cls))

    @classmethod
    def _fields(cls) -> set[str]:
        return cls._FIELDS_CACHE.setdefault(
            cls,
            {k for k in cls._schema() if not k.startswith("_")},
        )

    @staticmethod
    def _is_optional(tp: type) -> bool:
        if get_origin(tp) in (Union, UnionType):
            return type(None) in get_args(tp)
        return False

    def __init__(self, data: MutableMapping[str, Any]):
        object.__setattr__(self, "_data", data)
        object.__setattr__(self, "_children", {})
        for key, tp in self._schema().items():
            if key.startswith("_"):
                continue
            if key in data:
                continue
            if hasattr(self.__class__, key):
                continue
            if self._is_optional(tp):
                continue
            logger.warning(f"[config:{self.__class__.__name__}] 缺少字段: {key}")

    def __getattr__(self, key: str) -> Any:
        if key in self._fields():
            value = self._data.get(key)
            tp = self._schema().get(key)

            if isinstance(tp, type) and issubclass(tp, ConfigNode):
                children: dict[str, ConfigNode] = self.__dict__["_children"]
                if key not in children:
                    if not isinstance(value, MutableMapping):
                        raise TypeError(
                            f"[config:{self.__class__.__name__}] "
                            f"字段 {key} 期望 dict，实际是 {type(value).__name__}"
                        )
                    children[key] = tp(value)
                return children[key]

            return value

        if key in self.__dict__:
            return self.__dict__[key]

        raise AttributeError(key)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self._fields():
            self._data[key] = value
            return
        object.__setattr__(self, key, value)

    def save_config(self) -> None:
        """
        保存配置到磁盘（仅允许在根节点调用）
        """
        if not isinstance(self._data, AstrBotConfig):
            raise RuntimeError(
                f"{self.__class__.__name__}.save_config() 只能在根配置节点上调用"
            )
        self._data.save_config()


# ============ 插件自定义配置 ==================


class LLMConfig(ConfigNode):
    comment_prompt: str
    reply_prompt: str


class SourceConfig(ConfigNode):
    ignore_groups: list[str]
    ignore_users: list[str]

    def is_ignore_group(self, group_id: str) -> bool:
        return group_id in self.ignore_groups

    def is_ignore_user(self, user_id: str) -> bool:
        return user_id in self.ignore_users


class TriggerConfig(ConfigNode):
    auto_trigger_enabled: bool
    read_prob: float
    send_admin: bool
    like_when_comment: bool

    @property
    def auto_enabled(self) -> bool:
        return bool(self._data.get("auto_trigger_enabled", False))


class ConnectionConfig(ConfigNode):
    cookie_ttl: int
    timeout: int


class PollingConfig(ConfigNode):
    enabled: bool
    interval: int
    batch_limit: int


class PluginConfig(ConfigNode):
    llm: LLMConfig
    source: SourceConfig
    trigger: TriggerConfig
    connection: ConnectionConfig
    polling: PollingConfig
    debug_mode: bool

    _DB_VERSION = 5
    _plugin_name = "astrbot_plugin_qzone"

    def __init__(self, cfg: AstrBotConfig, context: Context):
        self._migrate_legacy_config(cfg)
        super().__init__(cfg)
        self.context = context
        self.data_dir = Path(get_astrbot_plugin_data_path()) / self._plugin_name
        self.temp_dir = Path(get_astrbot_temp_path()) / self._plugin_name
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.data_dir / f"posts_{self._DB_VERSION}.db"

        self.emoji_cdn = (
            "https://cdn.jsdelivr.net/npm/emoji-datasource-facebook@14.0.0/"
            "img/facebook/64/"
        )
        self.emoji_style = "FACEBOOK"

        self.admins_id: list[str] = context.get_config().get("admins_id", [])
        self._normalize_id()
        self.admin_id = self.admins_id[0] if self.admins_id else None
        self.save_config()

    @staticmethod
    def _migrate_legacy_config(cfg: AstrBotConfig) -> None:
        """Move legacy root settings into their new groups, retaining custom values."""
        migrations = {
            "cookie_ttl": ("connection", "cookie_ttl", 600),
            "timeout": ("connection", "timeout", 10),
            "poll_enabled": ("polling", "enabled", False),
            "poll_interval": ("polling", "interval", 30),
            "poll_batch_limit": ("polling", "batch_limit", 5),
        }
        for old_key, (group, new_key, default) in migrations.items():
            if old_key not in cfg:
                continue
            group_data = cfg.get(group)
            if not isinstance(group_data, MutableMapping):
                group_data = {}
                cfg[group] = group_data
            old_value = cfg.pop(old_key)
            if new_key not in group_data or group_data[new_key] == default:
                group_data[new_key] = old_value

    def _normalize_id(self):
        """仅保留纯数字ID"""
        for ids in [
            self.admins_id,
            self.source.ignore_groups,
            self.source.ignore_users,
        ]:
            normalized = []
            for raw in ids:
                s = str(raw)
                if s.isdigit():
                    normalized.append(s)
            ids.clear()
            ids.extend(normalized)
