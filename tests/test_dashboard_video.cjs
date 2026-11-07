const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.classList = { add() {}, remove() {} };
  }

  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  addEventListener() {}
  setAttribute() {}
}

const elements = new Map();
const document = {
  getElementById(id) { return elements.get(id) || null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  createElement(tagName) { return new Element(tagName); },
  body: { appendChild(element) { elements.set(element.id, element); } },
};

const scriptPath = path.join(__dirname, "..", "pages", "dashboard", "app.js");
const script = fs.readFileSync(scriptPath, "utf8").replace(/\binit\(\);\s*$/, "");
const context = vm.createContext({ window: {}, document, setTimeout() {} });
vm.runInContext(script, context);

function mediaNodes(element) {
  return [
    ...(element.tagName === "video" || element.tagName === "img" ? [element] : []),
    ...element.children.flatMap(mediaNodes),
  ];
}

test("post cards and lightbox recognize signed video URLs", () => {
  const url = "https://example.test/clip.f0.mp4?dis_k=token&dis_t=123#view";
  context.testPost = {
    id: "post",
    author: { nickname: "Author" },
    content: "Video",
    images: [url],
    stats: {},
  };
  const card = vm.runInContext("renderPostCard(testPost)", context);
  const media = mediaNodes(card);
  assert.equal(media.length, 1);
  assert.equal(media[0].tagName, "video");
  assert.equal(media[0].src, url);

  context.testUrl = url;
  vm.runInContext("openLightbox(testUrl)", context);
  const lightbox = elements.get("lightbox");
  const video = mediaNodes(lightbox)[0];
  assert.equal(video.tagName, "video");
  assert.equal(video.src, url);
  assert.equal(video.controls, true);
});

test("image URLs containing a video suffix in a query stay images", () => {
  context.testUrl = "https://example.test/image.jpg?name=clip.mp4";
  assert.equal(vm.runInContext("isVideoUrl(testUrl)", context), false);
  assert.equal(vm.runInContext("isVideoUrl('https://example.test/clip.WEBM')", context), true);
});

test("explicit video metadata renders URLs without file extensions", () => {
  context.testPost = {
    id: "album",
    author: { nickname: "Author" },
    images: [],
    videos: ["https://example.test/play?token=x"],
    read_only: true,
    stats: {},
  };
  const card = vm.runInContext("renderPostCard(testPost)", context);
  const media = mediaNodes(card);
  assert.equal(media.length, 1);
  assert.equal(media[0].tagName, "video");
});
