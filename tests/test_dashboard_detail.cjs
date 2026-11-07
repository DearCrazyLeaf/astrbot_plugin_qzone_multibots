const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tagName = "div", text = "") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.classList = {
      add() {},
      remove() {},
      toggle() {},
    };
    this.textContent = text;
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
  setAttribute(name, value) { this[name] = value; }
}

const document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tagName) => new Element(tagName),
  createTextNode: (text) => new Element("#text", text),
};
const script = fs.readFileSync(
  path.join(__dirname, "..", "pages", "dashboard", "app.js"),
  "utf8",
).replace(/\binit\(\);\s*$/, "");
const context = vm.createContext({ window: {}, document });
vm.runInContext(script, context);

test("post media does not render the same URL twice across image and video fields", () => {
  const post = {
    images: [
      "https://example.test/clip.mp4?token=1",
      "https://example.test/photo.jpg?size=small",
      "https://example.test/photo.jpg?size=large",
    ],
    videos: ["https://example.test/clip.mp4?token=1"],
  };
  context.testPost = post;

  const media = vm.runInContext("renderPostMedia(testPost)", context);
  assert.equal(media.children.length, 2);
  assert.equal(media.children[0].tagName, "VIDEO");
  assert.equal(media.children[1].tagName, "IMG");
  assert.deepEqual(post.images, [
    "https://example.test/clip.mp4?token=1",
    "https://example.test/photo.jpg?size=small",
    "https://example.test/photo.jpg?size=large",
  ]);
  assert.deepEqual(post.videos, ["https://example.test/clip.mp4?token=1"]);
});

test("QQ emoticon markers in comments render as inline emoji images", () => {
  const row = vm.runInContext(`renderComment(
    { id: "post", read_only: true },
    { id: "comment", author: { nickname: "Alice" }, content: "Hi [em]e100[/em]!" },
  )`, context);
  const commentText = row.children[1].children[1];

  assert.equal(commentText.className, "comment-content");
  assert.equal(commentText.children.length, 3);
  assert.equal(commentText.children[0].textContent, "Hi ");
  assert.equal(commentText.children[1].tagName, "IMG");
  assert.equal(commentText.children[1].src, "https://qzonestyle.gtimg.cn/qzone/em/e100.gif");
  assert.equal(commentText.children[2].textContent, "!");
});

test("appending a feed page ignores overlapping posts", () => {
  const posts = vm.runInContext(`appendUniquePosts(
    [{ id: "first" }, { id: "second" }],
    [{ id: "second" }, { id: "third" }],
  )`, context);

  assert.deepEqual(Array.from(posts, (post) => post.id), ["first", "second", "third"]);
});

test("media URLs with different resource IDs remain distinct", () => {
  const media = vm.runInContext(`renderPostMedia({
    images: [
      "https://example.test/image?id=1",
      "https://example.test/image?id=2",
    ],
  })`, context);

  assert.equal(media.children.length, 2);
});
