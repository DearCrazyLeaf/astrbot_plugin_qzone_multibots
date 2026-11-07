import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from quart import Quart
from astrbot.core.config.astrbot_config import AstrBotConfig

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))
plugin_main = importlib.import_module(f"{PLUGIN_DIR.name}.main")


class SettingsAPITests(unittest.IsolatedAsyncioTestCase):
    async def test_all_settings_save_to_disk_and_reload(self):
        app = Quart(__name__)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"

            plugin = object.__new__(plugin_main.QzonePlugin)
            config = AstrBotConfig(
                config_path=str(path), schema=plugin_main.load_schema()
            )
            config["legacy_value"] = "keep"
            plugin.cfg = SimpleNamespace(_data=config, save_config=config.save_config)
            provider = SimpleNamespace(
                provider_config={"id": "vision"}, get_model=lambda: "vision-model"
            )
            plugin.context = SimpleNamespace(get_all_providers=lambda: [provider])
            async with app.test_request_context("/settings", method="GET"):
                response = await plugin.page_settings()
                data = (await response.get_json())["data"]
            values = data["values"]
            values["llm"]["comment_prompt"] = "changed"
            values["llm"]["reply_prompt"] = "changed reply"
            values["video"]["provider_id"] = "vision"
            values["trigger"]["auto_trigger_enabled"] = True
            values["trigger"]["read_prob"] = 0.5
            values["trigger"]["send_admin"] = True
            values["trigger"]["like_when_comment"] = False
            values["source"]["ignore_groups"] = ["12345"]
            values["source"]["ignore_users"] = ["54321"]
            values["polling"]["enabled"] = True
            values["polling"]["interval"] = 20
            values["polling"]["batch_limit"] = 4
            values["connection"]["cookie_ttl"] = 120
            values["connection"]["timeout"] = 15
            values["debug_mode"] = True
            async with app.test_request_context("/settings", method="POST", json={"values": values}):
                response = await plugin.page_settings()
                self.assertEqual(response.status_code, 200)
                self.assertEqual((await response.get_json())["data"]["values"], values)

            saved = json.loads(path.read_text(encoding="utf-8-sig"))
            self.assertEqual(saved, {"legacy_value": "keep", **values})
            self.assertEqual(data["providers"], [{"id": "vision", "model": "vision-model"}])
            plugin.cfg._data = saved
            async with app.test_request_context("/settings", method="GET"):
                response = await plugin.page_settings()
                self.assertEqual((await response.get_json())["data"]["values"], values)

            values["polling"]["interval"] = 13
            async with app.test_request_context("/settings", method="POST", json={"values": values}):
                response = await plugin.page_settings()
                self.assertEqual(response.status_code, 400)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8-sig")), saved)

    async def test_failed_save_restores_original_data_and_group_references(self):
        app = Quart(__name__)
        plugin = object.__new__(plugin_main.QzonePlugin)
        group = {"comment_prompt": "old"}
        original = {"llm": group, "legacy_value": "keep"}

        def fail_save():
            raise OSError("disk unavailable")

        plugin.cfg = SimpleNamespace(_data=original, save_config=fail_save)
        plugin.context = SimpleNamespace(get_all_providers=lambda: [])
        values = plugin_main.settings_values(original, plugin_main.load_schema())
        values["llm"]["comment_prompt"] = "new"
        async with app.test_request_context("/settings", method="POST", json={"values": values}):
            response = await plugin.page_settings()
            self.assertEqual(response.status_code, 400)
        self.assertEqual(original, {"llm": {"comment_prompt": "old"}, "legacy_value": "keep"})
        self.assertIs(original["llm"], group)
