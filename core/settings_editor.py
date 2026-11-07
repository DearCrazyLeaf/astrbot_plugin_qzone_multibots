"""Schema-driven settings validation for the plugin dashboard."""

import copy
import json
import math
from pathlib import Path
from typing import Any


def load_schema() -> dict[str, Any]:
    path = Path(__file__).resolve().parent.parent / "_conf_schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def settings_values(data: dict, schema: dict) -> dict:
    result = {}
    for key, meta in schema.items():
        if meta["type"] == "object":
            group = data.get(key)
            result[key] = settings_values(group if isinstance(group, dict) else {}, meta["items"])
        else:
            result[key] = copy.deepcopy(data.get(key, meta.get("default")))
    return result


def validate_settings(values: Any, schema: dict, prefix: str = "") -> dict:
    if not isinstance(values, dict) or set(values) != set(schema):
        raise ValueError(f"{prefix or '配置'}字段不完整或包含未知字段，请刷新后重试")
    result = {}
    for key, meta in schema.items():
        name = f"{prefix}.{key}" if prefix else key
        value = values[key]
        kind = meta["type"]
        if kind == "object":
            result[key] = validate_settings(value, meta["items"], name)
            continue
        valid = (
            (kind == "bool" and isinstance(value, bool))
            or (kind == "int" and type(value) is int)
            or (kind == "float" and type(value) in (int, float) and math.isfinite(value))
            or (kind in ("string", "text") and isinstance(value, str))
            or (kind == "list" and isinstance(value, list) and all(isinstance(v, str) for v in value))
        )
        if not valid:
            raise ValueError(f"{name} 类型不正确")
        if "options" in meta and value not in meta["options"]:
            raise ValueError(f"{name} 不在允许的选项中")
        slider = meta.get("slider", {})
        if slider and not slider["min"] <= value <= slider["max"]:
            raise ValueError(f"{name} 超出允许范围")
        if name in ("source.ignore_groups", "source.ignore_users") and any(
            not item.isdigit() for item in value
        ):
            raise ValueError(f"{name} 必须填写数字 QQ 号")
        result[key] = value
    return result


def apply_settings(data: dict, values: dict) -> None:
    for key, value in values.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            apply_settings(data[key], value)
        else:
            data[key] = copy.deepcopy(value)


def restore_settings(data: dict, snapshot: dict) -> None:
    for key in list(data):
        if key not in snapshot:
            del data[key]
    for key, value in snapshot.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            restore_settings(data[key], value)
        else:
            data[key] = copy.deepcopy(value)
