const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const root = path.join(__dirname, "..");
const schema = JSON.parse(fs.readFileSync(path.join(root, "_conf_schema.json"), "utf8"));

function defaults(entries) {
  return Object.fromEntries(Object.entries(entries).map(([key, meta]) => [
    key, meta.type === "object" ? defaults(meta.items) : meta.default,
  ]));
}

function flatten(entries, prefix = "") {
  return Object.entries(entries).flatMap(([key, meta]) => {
    const name = prefix ? `${prefix}.${key}` : key;
    return meta.type === "object" ? flatten(meta.items, name) : [name];
  });
}

class Element {
  constructor(tagName) {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
  showModal() { this.open = true; }
  close() { this.open = false; }
}

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}

test("all schema settings render and round-trip through save and reopen", async () => {
  let saved = defaults(schema);
  const elements = new Map([
    ["settingsForm", new Element("form")],
    ["settingsFields", new Element("div")],
    ["settingsDialog", new Element("dialog")],
    ["settingsError", new Element("p")],
    ["notice", new Element("div")],
  ]);
  elements.get("notice").classList = { add() {} };
  const bridge = {
    apiGet: async (endpoint) => endpoint === "page/settings"
      ? { ok: true, data: { schema, values: saved, providers: [{ id: "vision", model: "model" }] } }
      : { ok: true, data: { debug: saved.debug_mode } },
    apiPost: async (_endpoint, body) => {
      saved = structuredClone(body.values);
      return { ok: true, data: {} };
    },
  };
  const document = {
    getElementById: (id) => elements.get(id) || null,
    querySelector: () => null,
    querySelectorAll: () => [],
    createElement: (tag) => new Element(tag),
  };
  const context = vm.createContext({
    window: { AstrBotPluginPage: bridge, setTimeout, clearTimeout }, document,
  });
  const script = fs.readFileSync(path.join(root, "pages", "dashboard", "app.js"), "utf8")
    .replace(/\binit\(\);\s*$/, "");
  vm.runInContext(script, context);

  await vm.runInContext("openSettings()", context);
  const controls = descendants(elements.get("settingsFields"))
    .filter((element) => element.dataset.configPath);
  assert.deepEqual(controls.map((control) => control.dataset.configPath).sort(), flatten(schema).sort());

  const changes = {
    "llm.comment_prompt": "changed comment",
    "llm.reply_prompt": "changed reply",
    "video.provider_id": "vision",
    "video.max_videos": 4,
    "video.max_download_mb": 50,
    "video.max_duration_seconds": 120,
    "video.frame_interval_seconds": 5,
    "video.max_frames": 8,
    "video.max_frame_dimension": 1024,
    "video.provider_timeout_seconds": 90,
    "trigger.auto_trigger_enabled": true,
    "trigger.read_prob": "0.5",
    "trigger.send_admin": true,
    "trigger.like_when_comment": false,
    "source.ignore_groups": "12345\n67890",
    "source.ignore_users": "54321",
    "polling.enabled": true,
    "polling.interval": "20",
    "polling.batch_limit": "4",
    "connection.cookie_ttl": "120",
    "connection.timeout": "15",
    "debug_mode": true,
  };
  assert.deepEqual(Object.keys(changes).sort(), flatten(schema).sort());
  for (const control of controls) {
    const value = changes[control.dataset.configPath];
    if (control.type === "checkbox") control.checked = value;
    else control.value = value;
  }
  assert.ok(descendants(elements.get("settingsFields"))
    .some((element) => element.tagName === "OPTION" && element.value === "vision"));

  await elements.get("settingsForm").onsubmit({ preventDefault() {} });
  assert.equal(elements.get("settingsDialog").open, false);
  assert.equal(saved.video.provider_id, "vision");
  assert.equal(saved.polling.interval, 20);
  assert.deepEqual(saved.source.ignore_groups, ["12345", "67890"]);
  assert.equal(saved.debug_mode, true);

  await vm.runInContext("openSettings()", context);
  const reopened = descendants(elements.get("settingsFields"))
    .filter((element) => element.dataset.configPath);
  for (const control of reopened) {
    const expected = changes[control.dataset.configPath];
    const actual = control.type === "checkbox" ? control.checked : String(control.value);
    assert.equal(actual, control.type === "checkbox" ? expected : String(expected));
  }
});
