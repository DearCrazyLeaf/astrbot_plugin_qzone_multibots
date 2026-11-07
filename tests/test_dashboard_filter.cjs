const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor() {
    this.children = [];
    this.value = "";
    this.dataset = {};
  }
  setAttribute(name, value) { this[name] = value; }
  replaceChildren(...children) { this.children = children; }
  append(...children) { this.children.push(...children); }
}

const elements = new Map([
  "targetUin", "clearTarget", "filterHelp", "feedTitle", "feedMeta", "feed",
  "moreButton", "statusFeed", "crumb",
].map((id) => [id, new Element()]));
const document = {
  getElementById: (id) => elements.get(id) || null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => new Element(),
};
const source = fs.readFileSync(path.join(__dirname, "..", "pages", "dashboard", "app.js"), "utf8")
  .replace(/\binit\(\);\s*$/, "");
const context = vm.createContext({ window: {}, document });
vm.runInContext(source, context);
vm.runInContext(`
  renderPostCard = post => ({ id: post.id });
  state.posts = [
    { id: "video", author: { uin: 10001 }, has_video: true },
    { id: "image", author: { uin: 10002 }, images: ["image"] },
  ];
`, context);

test("friend QQ and media filters compose and report invalid input", () => {
  const input = elements.get("targetUin");
  input.value = "10001";
  vm.runInContext("renderFeed()", context);
  assert.deepEqual(elements.get("feed").children.map((item) => item.id), ["video"]);
  vm.runInContext('state.feedFilter = "image"; renderFeed()', context);
  assert.equal(elements.get("feed").children[0].textContent, "当前已加载的动态中没有匹配结果。");
  input.value = "abc";
  vm.runInContext("renderFeed()", context);
  assert.equal(input["aria-invalid"], "true");
  assert.equal(elements.get("feed").children[0].textContent, "请输入数字 QQ 号。");
  input.value = "";
  vm.runInContext('state.feedFilter = "all"; renderFeed()', context);
  assert.equal(elements.get("feed").children.length, 2);
});

test("profile lookup keeps its separate backend request and is not locally QQ-filtered", () => {
  elements.get("targetUin").value = "99999";
  vm.runInContext('state.scope = "profile"; state.targetUin = "99999"; renderFeed()', context);
  assert.equal(elements.get("feed").children.length, 2);
  const params = vm.runInContext("feedParams()", context);
  assert.equal(params.scope, "profile");
  assert.equal(params.hostuin, "99999");
});

test("video filter recognizes video URLs in image metadata", () => {
  vm.runInContext(`
    state.scope = "friends";
    state.feedFilter = "video";
    state.posts = [{ id: "signed-video", author: { uin: 10001 }, images: ["https://example.test/a.mp4?token=1"] }];
  `, context);
  elements.get("targetUin").value = "";
  vm.runInContext("renderFeed()", context);
  assert.equal(elements.get("feed").children[0].id, "signed-video");
});

test("load more button is visible when another page is available", () => {
  const moreButton = elements.get("moreButton");
  vm.runInContext("state.posts = []; state.hasMore = true; renderFeed()", context);
  assert.equal(moreButton.hidden, false);

  vm.runInContext("state.hasMore = false; renderFeed()", context);
  assert.equal(moreButton.hidden, true);
});
