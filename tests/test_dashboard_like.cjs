const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor() {
    this.children = [];
    this.dataset = {};
  }
  addEventListener() {}
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this[name] = value; }
}

const document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => new Element(),
};
const script = fs.readFileSync(
  path.join(__dirname, "..", "pages", "dashboard", "app.js"),
  "utf8",
).replace(/\binit\(\);\s*$/, "");
const context = vm.createContext({ window: {}, document });
vm.runInContext(script, context);
context.testCalls = [];
vm.runInContext(`
  renderFeed = () => {};
  renderSelectedIfNeeded = () => {};
  setNotice = () => {};
  apiPost = async (_endpoint, body) => {
    testCalls.push(body);
    if (testCalls.length === 1) {
      return { verified: false, operation_status: "accepted_unverified", liked: false };
    }
    return {
      operation_status: "pending_verification",
      liked: true,
      message: "上一次点赞请求尚未回读确认，请重新查询后再操作",
    };
  };
`, context);

test("pending like verification prevents a second optimistic unlike", async () => {
  vm.runInContext(`
    state.posts = [{ id: "post", liked: false, stats: { likes: 3, comments: 0 } }];
    state.selected = null;
    state.likeState.clear();
  `, context);

  await vm.runInContext("toggleLike(state.posts[0])", context);
  assert.equal(vm.runInContext('state.likeState.get("post")', context), "liked");
  assert.equal(vm.runInContext("state.posts[0].stats.likes", context), 4);
  assert.equal(context.testCalls[0].unlike, false);

  await vm.runInContext("toggleLike(state.posts[0])", context);
  assert.equal(vm.runInContext('state.likeState.get("post")', context), "liked");
  assert.equal(vm.runInContext("state.posts[0].stats.likes", context), 4);
  assert.equal(context.testCalls[1].unlike, true);
});

test("like and comment capabilities are evaluated independently", () => {
  assert.equal(vm.runInContext(
    "postCanLike({ can_like: true, read_only: true })",
    context,
  ), true);
  assert.equal(vm.runInContext(
    "postCanLike({ read_only: true })",
    context,
  ), false);
  assert.equal(vm.runInContext(
    "postCanComment({ can_comment: true, read_only: true })",
    context,
  ), true);
  assert.equal(vm.runInContext(
    "postCanComment({ read_only: true })",
    context,
  ), false);
});
