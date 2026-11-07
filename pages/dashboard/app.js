const bridge = window.AstrBotPluginPage;
const BRIDGE_READY_TIMEOUT_MS = 5000;
const BRIDGE_REQUEST_TIMEOUT_MS = 20000;

const state = {
  context: null,
  status: null,
  account: "",
  accounts: [],
  scope: "friends",
  targetUin: "",
  feedFilter: "all",
  cursor: "",
  hasMore: false,
  posts: [],
  selected: null,
  media: [],
  loading: false,
  pendingLikes: new Set(),
  likeState: new Map(),
  knownAuthors: new Map(),
  replyTarget: null,
  replyDrafts: new Map(),
  pendingReplies: new Set(),
  localVersions: new Map(),
  detailRequestSeq: 0,
  detailLoadingId: "",
};

function queryOne(selector) {
  return typeof document.querySelector === "function" ? document.querySelector(selector) : null;
}

function queryAll(selector) {
  return typeof document.querySelectorAll === "function" ? [...document.querySelectorAll(selector)] : [];
}

const el = {
  statusText: document.getElementById("statusText"),
  accountName: document.getElementById("accountName"),
  accountMeta: document.getElementById("accountMeta"),
  accountAvatar: queryOne(".account .avatar"),
  accountMenu: document.getElementById("accountMenu"),
  accountAvatarBtn: document.getElementById("accountAvatarBtn"),
  themeToggle: document.getElementById("themeToggle"),
  debugToggle: document.getElementById("debugToggle"),
  settingsButton: document.getElementById("settingsButton"),
  settingsDialog: document.getElementById("settingsDialog"),
  settingsForm: document.getElementById("settingsForm"),
  settingsFields: document.getElementById("settingsFields"),
  settingsError: document.getElementById("settingsError"),
  settingsClose: document.getElementById("settingsClose"),
  tabs: queryAll(".tab"),
  targetForm: document.getElementById("targetForm"),
  targetUin: document.getElementById("targetUin"),
  clearTarget: document.getElementById("clearTarget"),
  filterHelp: document.getElementById("filterHelp"),
  filters: queryAll("[data-filter]"),
  statusFeed: document.getElementById("statusFeed"),
  statusActivity: document.getElementById("statusActivity"),
  crumb: document.getElementById("crumb"),
  sidebarToggle: document.getElementById("sidebarToggle"),
  paletteButton: document.getElementById("paletteButton"),
  paletteDialog: document.getElementById("paletteDialog"),
  paletteClose: document.getElementById("paletteClose"),
  paletteDone: document.getElementById("paletteDone"),
  paletteReset: document.getElementById("paletteReset"),
  colorOne: document.getElementById("colorOne"),
  colorTwo: document.getElementById("colorTwo"),
  gradient: document.getElementById("gradient"),
  gradientValue: document.getElementById("gradientValue"),
  publishForm: document.getElementById("publishForm"),
  publishContent: document.getElementById("publishContent"),
  mediaInput: document.getElementById("mediaInput"),
  mediaStrip: document.getElementById("mediaStrip"),
  publishButton: document.getElementById("publishButton"),
  refreshButton: document.getElementById("refreshButton"),
  feedTitle: document.getElementById("feedTitle"),
  feedMeta: document.getElementById("feedMeta"),
  notice: document.getElementById("notice"),
  feed: document.getElementById("feed"),
  moreButton: document.getElementById("moreButton"),
  detailPane: document.getElementById("detailPane"),
  detailDialog: document.getElementById("detailDialog"),
  detailClose: document.getElementById("detailClose"),
  detailEmpty: document.getElementById("detailEmpty"),
  detailContent: document.getElementById("detailContent"),
};

const THEME_STORAGE_KEY = "qzone-dashboard-theme";
const PALETTE_STORAGE_KEY = "qzone-dashboard-palette";
const PALETTE_DEFAULT = { one: "#e1b34e", two: "#bb7a14", strength: 70 };

function updatePalette(persist = false) {
  const one = el.colorOne.value;
  const two = el.colorTwo.value;
  const strength = Number(el.gradient.value);
  const style = document.documentElement.style;
  style.setProperty("--color-one", one);
  style.setProperty("--color-two", two);
  style.setProperty("--gradient-mix", `${strength}%`);
  style.setProperty("--tint", `${15 + Math.round(strength * 0.3)}%`);
  el.gradientValue.value = `${strength}%`;
  if (persist) {
    try { localStorage.setItem(PALETTE_STORAGE_KEY, JSON.stringify({ one, two, strength })); }
    catch (error) { console.warn("无法保存仪表盘配色", error); }
  }
}

function initializePalette() {
  if (!el.colorOne || !el.colorTwo || !el.gradient || !el.gradientValue) return;
  try {
    const saved = JSON.parse(localStorage.getItem(PALETTE_STORAGE_KEY) || "null");
    if (saved && /^#[0-9a-f]{6}$/i.test(saved.one) && /^#[0-9a-f]{6}$/i.test(saved.two)
      && Number.isInteger(saved.strength) && saved.strength >= 0 && saved.strength <= 100) {
      el.colorOne.value = saved.one;
      el.colorTwo.value = saved.two;
      el.gradient.value = saved.strength;
    }
  } catch (error) { console.warn("无法读取仪表盘配色", error); }
  updatePalette();
}

function closeOnBackdrop(dialog) {
  dialog?.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right
      || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
  });
}

function applyTheme(theme, persist = false) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  if (el.themeToggle) {
    const label = el.themeToggle.querySelector("span");
    const icon = el.themeToggle.querySelector("#themeIcon");
    if (label) label.textContent = dark ? "亮色模式" : "暗色模式";
    if (icon) icon.setAttribute("d", dark ? "M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4m0-12.8L17 7M7 17l-1.4 1.4M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" : "M20 14a8 8 0 0 1-10-10 8 8 0 1 0 10 10Z");
    el.themeToggle.setAttribute("aria-pressed", String(dark));
    el.themeToggle.setAttribute("aria-label", dark ? "切换亮色模式" : "切换暗色模式");
  }
  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, dark ? "dark" : "light"); } catch (error) { /* 存储不可用时仅保留本次设置 */ }
  }
}

function initializeTheme() {
  let saved = "";
  try { saved = localStorage.getItem(THEME_STORAGE_KEY) || ""; } catch (error) { /* 使用系统偏好 */ }
  const systemDark = typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved === "dark" || saved === "light" ? saved : (systemDark ? "dark" : "light"));
}

function text(value) {
  return String(value ?? "");
}

function getAvatarUrl(uin) {
  if (!uin) return "";
  return `https://q.qlogo.cn/headimg_dl?dst_uin=${encodeURIComponent(uin)}&spec=100`;
}

function getFallbackAvatarUrl(uin) {
  if (!uin) return "";
  return `https://q1.qlogo.cn/g?b=qq&nk=${encodeURIComponent(uin)}&s=100`;
}

function normalizeAvatarUrl(url) {
  const value = text(url).trim();
  if (!value) return "";
  if (value.startsWith("//")) return `https:${value}`;
  if (value.startsWith("http://")) return `https://${value.slice("http://".length)}`;
  return value;
}

function cleanDisplayText(value) {
  return text(value)
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n[ \t]+/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function authorKey(uin) {
  const value = Number(uin || 0);
  if (!Number.isFinite(value) || value <= 0) return "";
  return String(Math.trunc(value));
}

function isGenericNickname(value, uin = 0) {
  const name = text(value).trim();
  const key = authorKey(uin);
  return !name
    || name === "我"
    || name === "用户"
    || name === "QQ空间用户"
    || name === "QQ 空间用户"
    || (key && name === key)
    || /^QQ\s*\d{5,}$/i.test(name)
    || /^\d{5,}$/.test(name);
}

function rememberAuthor(author) {
  const key = authorKey(author?.uin);
  if (!key) return;
  const nickname = text(author?.nickname).trim();
  if (isGenericNickname(nickname, key)) return;
  const remembered = { ...(state.knownAuthors.get(key) || {}), ...author, uin: Number(key), nickname };
  state.knownAuthors.set(key, remembered);

  const login = state.status?.login;
  if (login && authorKey(login.uin) === key && isGenericNickname(login.nickname, key)) {
    login.nickname = nickname;
  }
}

function rememberPostAuthors(post) {
  if (!post) return;
  rememberAuthor(post.author);
  for (const comment of post.comments || []) {
    rememberAuthor(comment.author);
  }
}

function rememberPosts(posts) {
  for (const post of posts || []) {
    rememberPostAuthors(post);
  }
}

function loginDisplayName() {
  const login = state.status?.login || {};
  const key = authorKey(login.uin);
  const known = key ? state.knownAuthors.get(key) : null;
  if (!isGenericNickname(login.nickname, key)) return text(login.nickname).trim();
  if (known && !isGenericNickname(known.nickname, key)) return known.nickname;
  if (login.bound || key) return "我";
  return "未绑定";
}

function currentLoginAuthor() {
  const login = state.status?.login || {};
  return {
    uin: login.uin || 0,
    nickname: loginDisplayName(),
    avatar: login.avatar || "",
  };
}

function displayAuthorName(author, fallback = "QQ空间用户") {
  const key = authorKey(author?.uin);
  const known = key ? state.knownAuthors.get(key) : null;
  const login = state.status?.login || {};
  const loginKey = authorKey(login.uin);
  const name = text(author?.nickname).trim();

  if (key && loginKey && key === loginKey) {
    return loginDisplayName();
  }
  if (!isGenericNickname(name, key)) return name;
  if (known && !isGenericNickname(known.nickname, key)) return known.nickname;
  return fallback;
}

function mergeAuthor(base, patch) {
  const merged = { ...(base || {}), ...(patch || {}) };
  const key = authorKey(merged.uin || base?.uin || patch?.uin);
  if (isGenericNickname(merged.nickname, key) && !isGenericNickname(base?.nickname, key)) {
    merged.nickname = base.nickname;
  }
  if (!merged.avatar && base?.avatar) {
    merged.avatar = base.avatar;
  }
  return merged;
}

function commentKey(comment) {
  const id = text(comment?.id || comment?.commentid).trim();
  if (id) return `id:${id}`;
  return [
    "body",
    authorKey(comment?.author?.uin),
    text(comment?.content).trim(),
    text(comment?.created_at),
  ].join(":");
}

function mergeComment(base, patch) {
  const merged = { ...(base || {}), ...(patch || {}) };
  if (base?.author || patch?.author) {
    merged.author = mergeAuthor(base?.author, patch?.author);
  }
  if (!cleanDisplayText(merged.content) && cleanDisplayText(base?.content)) {
    merged.content = base.content;
  }
  return merged;
}

function mergeCommentsPreservingLocal(localComments = [], remoteComments = []) {
  const localByKey = new Map();
  for (const item of localComments || []) {
    localByKey.set(commentKey(item), item);
  }

  const merged = [];
  const seen = new Set();
  for (const remote of remoteComments || []) {
    const key = commentKey(remote);
    seen.add(key);
    merged.push(mergeComment(localByKey.get(key), remote));
  }
  for (const local of localComments || []) {
    const key = commentKey(local);
    if (!seen.has(key)) {
      merged.push(local);
    }
  }
  return merged;
}

function localVersion(id) {
  return Number(state.localVersions.get(id) || 0);
}

function markLocalChange(id) {
  if (!id) return;
  state.localVersions.set(id, localVersion(id) + 1);
}

function mergeRemotePost(id, remotePost, versionAtRequestStart) {
  const current = currentPostById(id || remotePost?.id);
  if (!current || localVersion(current.id) === versionAtRequestStart) {
    return remotePost;
  }

  const merged = mergePost(remotePost, {
    stats: current.stats,
    liked: current.liked,
    comments: mergeCommentsPreservingLocal(current.comments || [], remotePost.comments || []),
  });
  merged.id = remotePost.id;
  return merged;
}

function avatarUrlsFor(author) {
  const urls = [
    normalizeAvatarUrl(author?.avatar),
    getAvatarUrl(author?.uin),
    getFallbackAvatarUrl(author?.uin),
  ].filter(Boolean);
  return [...new Set(urls)];
}

function renderAvatar(target, author, fallbackName = "Q") {
  const initial = text(fallbackName || "Q").trim().slice(0, 1).toUpperCase() || "Q";
  const fallback = () => {
    target.classList.remove("has-image");
    target.replaceChildren();
    target.textContent = initial;
  };
  const urls = avatarUrlsFor(author);
  if (!urls.length) {
    fallback();
    return;
  }

  let index = 0;
  const img = document.createElement("img");
  img.alt = "";
  img.loading = "lazy";
  img.decoding = "async";
  img.onerror = () => {
    index += 1;
    if (index < urls.length) {
      img.src = urls[index];
      return;
    }
    fallback();
  };
  target.textContent = "";
  target.classList.add("has-image");
  target.replaceChildren(img);
  img.src = urls[index];
}

function mergePost(base, patch) {
  const merged = { ...(base || {}), ...(patch || {}) };
  if (base?.author || patch?.author) {
    merged.author = mergeAuthor(base?.author, patch?.author);
  }
  if (base?.stats || patch?.stats) {
    merged.stats = { ...(base?.stats || {}), ...(patch?.stats || {}) };
  }
  return merged;
}

function updatePost(id, patch) {
  let updated = null;
  state.posts = state.posts.map((item) => {
    if (item.id !== id) return item;
    updated = mergePost(item, patch);
    return updated;
  });
  if (state.selected?.id === id) {
    state.selected = mergePost(state.selected, patch);
    updated = state.selected;
  }
  return updated;
}

function currentPostById(id, fallback = null) {
  return state.posts.find((item) => item.id === id)
    || (state.selected?.id === id ? state.selected : null)
    || fallback;
}

function renderSelectedIfNeeded(id) {
  if (state.selected?.id === id) {
    renderDetail(state.selected);
  }
}

function setNotice(message, tone = "info") {
  el.notice.hidden = !message;
  el.notice.textContent = message || "";
  el.notice.dataset.tone = tone;
  el.notice.className = "notice";
  if (message && tone) {
    el.notice.classList.add(tone);
  }
}

async function withTimeout(promise, timeoutMs, message) {
  let timeoutId;
  const timeout = new Promise((_, reject) => {
    timeoutId = window.setTimeout(() => reject(new Error(message)), timeoutMs);
  });
  try {
    return await Promise.race([promise, timeout]);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function normalizeBridgeResult(result, fallbackMessage) {
  if (result && typeof result === "object") {
    if (result.status === "error") {
      throw new Error(result.message || fallbackMessage);
    }
    if (Object.prototype.hasOwnProperty.call(result, "ok")) {
      if (!result.ok) {
        throw new Error(result.error?.message || result.message || fallbackMessage);
      }
      return result.data || {};
    }
  }
  return result || {};
}

function accountParams(extra = {}) {
  return state.account ? { account: state.account, ...extra } : { ...extra };
}

async function apiGet(endpoint, params = {}) {
  const result = await withTimeout(
    bridge.apiGet(endpoint, accountParams(params)),
    BRIDGE_REQUEST_TIMEOUT_MS,
    "请求 AstrBot WebUI 超时，请刷新页面后重试。"
  );
  return normalizeBridgeResult(result, "请求失败");
}

async function apiPost(endpoint, body = {}) {
  const result = await withTimeout(
    bridge.apiPost(endpoint, accountParams(body)),
    BRIDGE_REQUEST_TIMEOUT_MS,
    "请求 AstrBot WebUI 超时，请刷新页面后重试。"
  );
  return normalizeBridgeResult(result, "请求失败");
}

function formatTime(value) {
  const timestamp = Number(value || 0);
  if (!timestamp) return "未知时间";
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) return "未知时间";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function scopeTitle() {
  if (state.scope === "self") return "我的空间";
  if (state.scope === "profile") return state.targetUin ? `${state.targetUin} 的空间` : "指定 QQ";
  return "好友动态";
}

function mediaLayoutClass(count) {
  const safeCount = Math.max(1, Math.min(Number(count || 0), 9));
  return `media-layout-${safeCount}`;
}



function renderStatus() {
  const login = state.status?.login || {};
  rememberAuthor(login);
  el.accountName.textContent = loginDisplayName();
  el.accountMeta.textContent = login.uin ? `QQ ${login.uin}` : "需要先绑定 Cookie";
  if (el.statusText) {
    const daemon = state.status?.daemon || {};
    const connected = daemon.state === "ready";
    el.statusText.dataset.state = connected ? "ready" : "offline";
    el.statusText.setAttribute("aria-label", connected ? "连接正常" : "连接不可用");
    const label = el.statusText.querySelector(".status-label");
    if (label) label.textContent = connected ? "连接正常" : "连接不可用";
  }
  
  if (login.uin && el.accountAvatar) {
    renderAvatar(el.accountAvatar, login, loginDisplayName());
  }
}

function renderTabs() {
  for (const tab of el.tabs) {
    tab.classList.toggle("active", tab.dataset.scope === state.scope || (state.scope === "profile" && tab.dataset.scope === "friends"));
  }
  if (el.targetForm) el.targetForm.hidden = state.scope === "self";
}

function closeDetail() {
  state.detailRequestSeq++;
  state.detailLoadingId = "";
  state.selected = null;
  state.replyTarget = null;
  el.detailContent.hidden = true;
  el.detailEmpty.hidden = false;
  el.detailPane.classList.remove("has-selection");
  if (el.detailDialog?.open) el.detailDialog.close();
}

function renderMedia() {
  el.mediaStrip.replaceChildren();
  for (const [index, item] of state.media.entries()) {
    const chip = document.createElement("div");
    chip.className = "media-chip";
    const name = document.createElement("span");
    name.textContent = item.name || `图片 ${index + 1}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "移除";
    remove.addEventListener("click", () => {
      state.media.splice(index, 1);
      renderMedia();
    });
    chip.append(name, remove);
    el.mediaStrip.append(chip);
  }
}

function renderFeed() {
  el.feedTitle.textContent = scopeTitle();
  if (el.crumb) el.crumb.textContent = state.scope === "self" ? "我的空间" : "好友动态";
  const input = state.scope === "friends" ? text(el.targetUin?.value).trim() : "";
  const valid = !input || /^\d+$/.test(input);
  const posts = state.posts.filter((post) => {
    const hasVideo = postHasVideo(post);
    const kindMatch = state.feedFilter === "all" || (state.feedFilter === "video" ? hasVideo : !hasVideo);
    return kindMatch && (!input || (valid && text(post.author?.uin) === input));
  });
  if (el.targetUin) el.targetUin.setAttribute("aria-invalid", String(!valid));
  if (el.clearTarget) el.clearTarget.hidden = !text(el.targetUin?.value).trim();
  if (el.filterHelp) el.filterHelp.textContent = state.scope === "profile"
    ? "正在查看指定 QQ 的空间说说；清除后返回好友动态。"
    : valid ? "仅筛选当前已加载的动态；也可查询该 QQ 的空间说说。" : "请输入数字 QQ 号。";
  el.feedMeta.textContent = state.loading ? "加载中..." : `${posts.length} / ${state.posts.length} 条`;
  if (el.statusFeed) el.statusFeed.textContent = state.loading ? "正在加载动态" : `已加载 ${state.posts.length} 条${state.hasMore ? "，可继续加载" : ""}`;
  if (el.statusActivity) {
    const latest = state.posts[0];
    el.statusActivity.textContent = latest ? `最新动态：${displayAuthorName(latest.author)} · ${formatTime(latest.created_at)}` : "";
  }
  el.moreButton.hidden = !state.hasMore;
  el.feed.replaceChildren();

  if (!posts.length && !state.loading) {
    const empty = document.createElement("div");
    empty.className = "empty-feed";
    empty.textContent = !valid ? "请输入数字 QQ 号。" : state.posts.length ? "当前已加载的动态中没有匹配结果。" : "还没有读取到说说。";
    el.feed.append(empty);
    return;
  }

  for (const post of posts) {
    el.feed.append(renderPostCard(post));
  }
}

function isVideoUrl(url) {
  return /\.(mp4|webm|ogg)$/i.test(text(url).split(/[?#]/, 1)[0]);
}

function mediaIdentity(value) {
  const url = text(value).trim().split("#", 1)[0];
  const [path, query = ""] = url.split("?", 2);
  const transientParams = new Set([
    "auth_key", "expires", "height", "quality", "resolution", "sign",
    "signature", "size", "spec", "token", "tp", "width",
  ]);
  const stableQuery = query.split("&").filter((parameter) => {
    const key = parameter.split("=", 1)[0];
    let decodedKey = key;
    try {
      decodedKey = decodeURIComponent(key.replace(/\+/g, " "));
    } catch {}
    return !transientParams.has(decodedKey.toLowerCase());
  }).sort();
  const hostPath = path.replace(
    /^(https?:)?\/\/([^/]+)/i,
    (_match, scheme, host) => `${(scheme || "").toLowerCase()}//${host.toLowerCase()}`,
  );
  return `${hostPath}${stableQuery.length ? `?${stableQuery.join("&")}` : ""}`;
}

function postHasVideo(post) {
  return Boolean(post.has_video || post.videos?.length || post.images?.some(isVideoUrl));
}

function postIsLiked(post) {
  const liked = state.likeState.get(post.id);
  return liked === "liked" || (liked !== "unliked" && Boolean(post.liked));
}

function postCanLike(post) {
  return post.can_like == null ? !post.read_only : Boolean(post.can_like);
}

function postCanComment(post) {
  return post.can_comment == null ? !post.read_only : Boolean(post.can_comment);
}

function openLightbox(url, video = false) {
  let lightbox = document.getElementById("lightbox");
  if (!lightbox) {
    lightbox = document.createElement("div");
    lightbox.id = "lightbox";
    lightbox.className = "lightbox";
    
    const closeBtn = document.createElement("button");
    closeBtn.className = "lightbox-close";
    closeBtn.innerHTML = "×";
    closeBtn.onclick = () => {
      lightbox.classList.remove("visible");
      setTimeout(() => lightbox.remove(), 300);
    };
    
    lightbox.onclick = (e) => {
      if (e.target === lightbox) {
        lightbox.classList.remove("visible");
        setTimeout(() => lightbox.remove(), 300);
      }
    };
    
    document.body.appendChild(lightbox);
  }
  
  lightbox.innerHTML = "";
  
  const closeBtn = document.createElement("button");
  closeBtn.className = "lightbox-close";
  closeBtn.innerHTML = "×";
  closeBtn.onclick = () => {
    lightbox.classList.remove("visible");
    setTimeout(() => lightbox.remove(), 300);
  };
  
  let mediaElement;
  
  if (video || isVideoUrl(url)) {
    mediaElement = document.createElement("video");
    mediaElement.src = url;
    mediaElement.controls = true;
    mediaElement.autoplay = true;
  } else {
    mediaElement = document.createElement("img");
    mediaElement.src = url;
  }
  
  lightbox.appendChild(closeBtn);
  lightbox.appendChild(mediaElement);
  
  // Force a reflow
  void lightbox.offsetWidth;
  lightbox.classList.add("visible");
}

function renderPostMedia(post) {
  const mediaByUrl = new Map();
  for (const url of post.images || []) {
    const key = mediaIdentity(url);
    if (key && !mediaByUrl.has(key)) {
      mediaByUrl.set(key, { url, video: isVideoUrl(url) });
    }
  }
  for (const url of post.videos || []) {
    if (!url) continue;
    const key = mediaIdentity(url);
    const existing = mediaByUrl.get(key);
    if (existing) {
      existing.url = url;
      existing.video = true;
    } else {
      mediaByUrl.set(key, { url, video: true });
    }
  }
  const mediaItems = [...mediaByUrl.values()];
  if (mediaItems.length > 0) {
    const images = document.createElement("div");
    const mediaCount = mediaItems.length;
    images.className = `post-media media-grid ${mediaLayoutClass(mediaCount)}`;
    for (const { url, video } of mediaItems) {
      if (video) {
        const vid = document.createElement("video");
        vid.src = url;
        vid.className = "preview-video";
        vid.muted = true;
        vid.loop = true;
        vid.playsInline = true;
        vid.addEventListener("mouseenter", () => vid.play().catch(()=>{}));
        vid.addEventListener("mouseleave", () => {
          vid.pause();
          vid.currentTime = 0;
        });
        vid.addEventListener("click", (e) => {
          e.stopPropagation();
          openLightbox(url, true);
        });
        images.append(vid);
      } else {
        const img = document.createElement("img");
        img.loading = "lazy";
        img.alt = "说说图片";
        img.src = url;
        img.addEventListener("click", (e) => {
          e.stopPropagation();
          openLightbox(url);
        });
        images.append(img);
      }
    }
    return images;
  }
  return null;
}

function renderPostCard(post) {
  rememberPostAuthors(post);
  const card = document.createElement("article");
  card.className = "post";
  card.dataset.id = post.id;

  const head = document.createElement("button");
  head.className = "post-header";
  head.type = "button";
  head.addEventListener("click", () => openDetail(post.id));

  const avatar = document.createElement("span");
  avatar.className = "avatar";
  const authorName = displayAuthorName(post.author);
  renderAvatar(avatar, post.author, authorName);

  const meta = document.createElement("span");
  meta.className = "post-meta";
  const name = document.createElement("strong");
  name.textContent = authorName;
  const time = document.createElement("span");
  time.textContent = formatTime(post.created_at);
  meta.append(name, time);
  head.append(avatar, meta);

  card.append(head);

  const mediaLabel = document.createElement("span");
  mediaLabel.className = "media-label";
  mediaLabel.textContent = Number(post.appid) === 4
    ? (postHasVideo(post) ? "相册视频" : "相册动态")
    : postHasVideo(post) ? (post.images?.some((url) => !isVideoUrl(url)) ? "视频 + 图文" : "视频")
    : post.images?.length ? "图文" : "文字";
  card.append(mediaLabel);

  const contentText = cleanDisplayText(post.content);
  if (contentText) {
    const body = document.createElement("p");
    body.className = "post-content";
    body.textContent = contentText;
    card.append(body);
  }
  const media = renderPostMedia(post);
  if (media) card.append(media);

  const actions = document.createElement("div");
  actions.className = "post-actions";
  const like = document.createElement("button");
  like.type = "button";
  like.className = postIsLiked(post) ? "liked" : "";
  like.disabled = !postCanLike(post) || state.pendingLikes.has(post.id);
  like.setAttribute?.("aria-busy", state.pendingLikes.has(post.id) ? "true" : "false");
  like.setAttribute?.("aria-label", `${postIsLiked(post) ? "取消点赞" : "点赞"} ${post.stats?.likes ?? 0}`);

  const likeText = document.createElement("span");
  likeText.textContent = String(post.stats?.likes ?? 0);
  like.append(actionIcon("heart"), likeText);
  like.addEventListener("click", () => toggleLike(post));

  const comment = document.createElement("button");
  comment.type = "button";
  
  const commentText = document.createElement("span");
  commentText.textContent = String(post.stats?.comments ?? 0);
  
  comment.append(actionIcon("comment"), commentText);
  comment.setAttribute?.("aria-label", `评论 ${post.stats?.comments ?? 0}`);
  comment.disabled = !postCanComment(post);
  comment.addEventListener("click", () => openDetail(post.id, true));

  const detail = document.createElement("button");
  detail.type = "button";
  detail.textContent = "查看详情";
  detail.addEventListener("click", () => openDetail(post.id));
  
  actions.append(like, comment, detail);
  card.append(actions);
  
  return card;
}

function actionIcon(kind) {
  const icon = document.createElement("span");
  icon.className = "action-icon";
  icon.innerHTML = kind === "heart"
    ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 8c0 4-8 9-8 9S4 12 4 8a4 4 0 0 1 8-1 4 4 0 0 1 8 1Z"/></svg>'
    : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5h14v11H9l-4 3V5Zm3 4h8m-8 3h6"/></svg>';
  return icon;
}

function renderDetail(post, options = {}) {
  state.selected = mergePost(state.selected?.id === post.id ? state.selected : {}, post);
  post = state.selected;
  rememberPostAuthors(post);
  const isLoading = Boolean(options.loading || state.detailLoadingId === post.id);
  el.detailEmpty.hidden = true;
  el.detailContent.hidden = false;
  el.detailPane.classList.add("has-selection");
  el.detailContent.setAttribute?.("aria-busy", isLoading ? "true" : "false");
  el.detailContent.replaceChildren();

  const title = document.createElement("div");
  title.className = "detail-title";
  
  const titleHead = document.createElement("div");
  titleHead.className = "detail-header";
  
  const titleAvatar = document.createElement("span");
  titleAvatar.className = "avatar";
  const authorName = displayAuthorName(post.author);
  renderAvatar(titleAvatar, post.author, authorName);
  
  const titleMeta = document.createElement("div");
  titleMeta.className = "detail-meta";
  const name = document.createElement("strong");
  name.textContent = authorName;
  const time = document.createElement("span");
  time.textContent = formatTime(post.created_at);
  titleMeta.append(name, time);
  
  titleHead.append(titleAvatar, titleMeta);
  title.append(titleHead);

  el.detailContent.append(title);

  const contentText = cleanDisplayText(post.content);
  if (contentText) {
    const content = document.createElement("p");
    content.className = "post-content detail-text";
    content.textContent = contentText;
    el.detailContent.append(content);
  }
  const media = renderPostMedia(post);
  if (media) el.detailContent.append(media);
  if (post.has_video && !post.videos?.length) {
    const missing = document.createElement("p");
    missing.className = "muted";
    missing.textContent = "接口未提供视频播放地址";
    el.detailContent.append(missing);
  }

  const actions = document.createElement("div");
    actions.className = "detail-actions";
    titleHead.append(actions);
  const like = document.createElement("button");
  like.type = "button";
  like.className = postIsLiked(post) ? "liked" : "";
  const likeCount = document.createElement("span");
  likeCount.textContent = String(post.stats?.likes ?? 0);
  like.append(actionIcon("heart"), likeCount);
  like.disabled = !postCanLike(post) || state.pendingLikes.has(post.id);
  like.setAttribute?.("aria-busy", state.pendingLikes.has(post.id) ? "true" : "false");
  like.setAttribute?.("aria-label", `${postIsLiked(post) ? "取消点赞" : "点赞"} ${post.stats?.likes ?? 0}`);
  like.addEventListener("click", () => toggleLike(post));
  actions.append(like);
  if (post.can_delete) {
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "删除";
    del.addEventListener("click", () => deletePost(post));
    actions.append(del);
  }

  // // // el.detailContent.append(actions);

  const comments = document.createElement("div");
  comments.className = "comments";
  const commentsTitle = document.createElement("h2");
  commentsTitle.textContent = "全部评论";
  comments.append(commentsTitle);
  if (isLoading) {
    const loading = document.createElement("div");
    loading.className = "detail-loading";
    loading.textContent = "正在同步详情...";
    comments.append(loading);
  }
  for (const item of post.comments || []) {
    comments.append(renderComment(post, item));
  }
  if (!post.comments?.length && !isLoading) {
    const empty = document.createElement("p");
    empty.className = "muted";
    empty.textContent = "还没有人评论，快来抢沙发。";
    comments.append(empty);
  }

  const form = document.createElement("form");
  form.className = "comment-form";
  const input = document.createElement("textarea");
  input.rows = 3;
  input.placeholder = "写下你的评论...";
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "发送";
  form.append(input, submit);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendComment(post, input.value);
    input.value = "";
  });

  el.detailContent.append(comments);
  if (postCanComment(post)) el.detailContent.append(form);
}

function renderComment(post, comment) {
  rememberAuthor(comment.author);
  const row = document.createElement("div");
  row.className = "comment";
  const targetKey = `${post.id}:${text(comment.id)}`;
  
  const avatar = document.createElement("span");
  avatar.className = "avatar";
  const authorName = displayAuthorName(comment.author);
  renderAvatar(avatar, comment.author, authorName);
  
  const body = document.createElement("div");
  body.className = "comment-body";
  
  const name = document.createElement("strong");
  name.textContent = authorName;
  const content = document.createElement("p");
  content.className = "comment-content";
  appendCommentContent(content, comment.content);
  body.append(name, content);
  row.append(avatar, body);
  if (comment.can_reply) {
    const reply = document.createElement("button");
    reply.type = "button";
    reply.className = "reply-btn";
    reply.textContent = "回复";
    reply.addEventListener("click", () => {
      const commentId = text(comment.id);
      const isSameTarget = state.replyTarget?.postId === post.id
        && state.replyTarget?.commentId === commentId;
      state.replyTarget = isSameTarget ? null : { postId: post.id, commentId };
      renderSelectedIfNeeded(post.id);
      if (!isSameTarget) {
        setTimeout(() => {
          el.detailContent.querySelector(".reply-form textarea")?.focus();
        }, 0);
      }
    });
    row.append(reply);
  }
  if (state.replyTarget?.postId === post.id && state.replyTarget?.commentId === text(comment.id)) {
    const form = document.createElement("form");
    form.className = "reply-form";
    const input = document.createElement("textarea");
    input.rows = 2;
    input.placeholder = `回复 ${authorName}`;
    input.value = state.replyDrafts.get(targetKey) || "";
    input.addEventListener("input", () => {
      state.replyDrafts.set(targetKey, input.value);
    });
    const actions = document.createElement("div");
    actions.className = "reply-form-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost";
    cancel.textContent = "取消";
    cancel.addEventListener("click", () => {
      state.replyDrafts.delete(targetKey);
      state.replyTarget = null;
      renderSelectedIfNeeded(post.id);
    });
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "primary";
    submit.textContent = "发送回复";
    actions.append(cancel, submit);
    form.append(input, actions);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      const sent = await sendReply(post, comment, input.value);
      if (sent) {
        state.replyDrafts.delete(targetKey);
      } else {
        submit.disabled = false;
      }
    });
    row.append(form);
  }
  return row;
}

function appendCommentContent(target, value) {
  const content = cleanDisplayText(value);
  const emoticonPattern = /\[em\](e\d+)\[\/em\]/gi;
  let offset = 0;
  for (const match of content.matchAll(emoticonPattern)) {
    const index = match.index ?? 0;
    if (index > offset) {
      target.append(document.createTextNode(content.slice(offset, index)));
    }
    const emoticon = document.createElement("img");
    emoticon.className = "qzone-emoji";
    emoticon.src = `https://qzonestyle.gtimg.cn/qzone/em/${match[1].toLowerCase()}.gif`;
    emoticon.alt = "[表情]";
    emoticon.loading = "lazy";
    emoticon.decoding = "async";
    target.append(emoticon);
    offset = index + match[0].length;
  }
  if (offset < content.length) {
    target.append(document.createTextNode(content.slice(offset)));
  }
}

async function loadStatus() {
  const data = await apiGet("page/status");
  state.status = data;
  renderStatus();
}

async function loadAccounts() {
  if (!el.accountMenu) return;
  try {
    const data = await apiGet("page/accounts");
    const items = data?.data?.items || data?.items || [];
    state.accounts = items;
  } catch (error) {
    state.accounts = [];
  }
  renderAccountMenu();
}

function renderAccountMenu() {
  if (!el.accountMenu) return;
  el.accountMenu.replaceChildren();
  if (!state.accounts.length) {
    const empty = document.createElement("div");
    empty.className = "account-menu-item empty";
    empty.textContent = "单账号模式";
    el.accountMenu.append(empty);
    return;
  }
  for (const item of state.accounts) {
    const id = item.id || item.name || "";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `account-menu-item${id && id === state.account ? " active" : ""}`;
    const avatar = document.createElement("span");
    avatar.className = "avatar";
    const name = item.nickname || item.name || item.id || "QQ空间用户";
    renderAvatar(avatar, { uin: item.uin, avatar: item.avatar }, name);
    const info = document.createElement("span");
    info.className = "mi-text";
    const label = document.createElement("span");
    label.className = "mi-name";
    label.textContent = name;
    info.append(label);
    if (item.uin) {
      const uin = document.createElement("span");
      uin.className = "mi-uin";
      uin.textContent = `QQ ${item.uin}${item.bound ? "" : "（未绑定）"}`;
      info.append(uin);
    }
    btn.append(avatar, info);
    btn.addEventListener("click", async () => {
      el.accountMenu.hidden = true;
      if (!id || id === state.account) return;
      state.account = id;
      state.cursor = "";
      state.posts = [];
      closeDetail();
      state.media = [];
      state.likeState.clear();
      renderMedia();
      renderAccountMenu();
      try {
        await loadStatus();
        await loadFeed();
      } catch (error) {
        setNotice(error.message || "账号切换失败", "error");
      }
    });
    el.accountMenu.append(btn);
  }
}

function feedParams(next = false) {
  const params = { limit: 10 };
  if (next && state.cursor) params.cursor = state.cursor;
  if (state.scope === "friends") params.scope = "friends";
  if (state.scope === "self") params.scope = "self";
  if (state.scope === "profile") {
    params.scope = "profile";
    params.hostuin = state.targetUin;
  }
  return params;
}

function appendUniquePosts(existing, incoming) {
  const seen = new Set((existing || []).map((post) => text(post.id)).filter(Boolean));
  const appended = [];
  for (const post of incoming || []) {
    const id = text(post.id);
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    appended.push(post);
  }
  return [...(existing || []), ...appended];
}

async function loadFeed({ append = false } = {}) {
  if (state.scope === "profile" && !state.targetUin) {
    state.posts = [];
    state.cursor = "";
    state.hasMore = false;
    setNotice("输入 QQ 号后查看指定空间。", "warn");
    renderFeed();
    return;
  }
  
  // Only show loading if we're completely empty, otherwise let the spinner handle it gracefully
  if (!append) {
    state.loading = true;
    renderFeed();
  } else {
    el.moreButton.textContent = "加载中...";
    el.moreButton.disabled = true;
  }
  
  try {
    const data = await apiGet("page/feed", feedParams(append));
    state.cursor = data.cursor || "";
    state.hasMore = Boolean(data.has_more);
    state.posts = append
      ? appendUniquePosts(state.posts, data.items)
      : data.items || [];
    if (!append) state.likeState.clear();
    rememberPosts(state.posts);
    renderStatus();
    setNotice("");
  } catch (error) {
    setNotice(error.message || "动态加载失败", "error");
  } finally {
    state.loading = false;
    if (append) {
      el.moreButton.textContent = "加载更多";
      el.moreButton.disabled = false;
    }
    renderFeed();
  }
}

async function openDetail(id, focusComment = false) {
  const cached = currentPostById(id);
  const requestSeq = ++state.detailRequestSeq;
  const versionAtRequestStart = localVersion(id);
  if (state.selected?.id !== id) {
    state.replyTarget = null;
  }
  state.detailLoadingId = id;
  if (el.detailDialog && !el.detailDialog.open) el.detailDialog.showModal();
  if (cached) {
    renderDetail(cached, { loading: true });
    renderFeed();
    if (focusComment) {
      setTimeout(() => {
        el.detailContent.querySelector(".comment-form textarea")?.focus();
      }, 0);
    }
  }
  try {
    const data = await apiGet("page/detail", { id });
    if (requestSeq !== state.detailRequestSeq) return;
    state.detailLoadingId = "";
    const incoming = mergeRemotePost(data.post.id, data.post, versionAtRequestStart);
    const merged = updatePost(incoming.id, incoming) || incoming;
    rememberPostAuthors(merged);
    renderDetail(merged);
    renderFeed();
    if (focusComment) {
      setTimeout(() => {
        el.detailContent.querySelector(".comment-form textarea")?.focus();
      }, 0);
    }
  } catch (error) {
    if (requestSeq !== state.detailRequestSeq) return;
    state.detailLoadingId = "";
    if (cached) {
      renderDetail(currentPostById(id, cached));
    }
    setNotice(error.message || "详情加载失败", "error");
  }
}

async function toggleLike(post) {
  if (state.pendingLikes.has(post.id)) return;
  state.pendingLikes.add(post.id);
  const current = state.posts.find((item) => item.id === post.id) || state.selected || post;
  const oldStats = { ...(current.stats || { likes: 0, comments: 0 }) };
  const currentLiked = postIsLiked(current);
  const nextLiked = !currentLiked;
  renderFeed();
  renderSelectedIfNeeded(post.id);
  try {
    const data = await apiPost("page/like", { id: post.id, unlike: !nextLiked });
    if (data.operation_status === "skipped_unknown") {
      state.likeState.delete(post.id);
      updatePost(post.id, { liked: null, stats: oldStats });
      setNotice(data.message || "点赞状态未知，本次操作已跳过。", "warn");
      return;
    }
    if (data.operation_status === "pending_verification") {
      state.likeState.set(post.id, currentLiked ? "liked" : "unliked");
      updatePost(post.id, { liked: currentLiked, stats: oldStats });
      setNotice(data.message || "上次点赞请求尚未验证，请重新查询。", "warn");
      return;
    }
    const acceptedUnverified = data.operation_status === "accepted_unverified";
    const liked = acceptedUnverified ? nextLiked : Boolean(data.liked);
    state.likeState.set(post.id, liked ? "liked" : "unliked");
    const delta = liked === currentLiked ? 0 : (liked ? 1 : -1);
    updatePost(post.id, {
      liked,
      stats: { ...oldStats, likes: Math.max(0, Number(oldStats.likes || 0) + delta) },
    });
    markLocalChange(post.id);
    if (acceptedUnverified) {
      setNotice("QQ空间已受理请求，但点赞状态尚未验证；请到 QQ 空间确认。", "warn");
    } else if (data.already) {
      setNotice(data.message || "点赞状态未改变。", "warn");
    } else {
      setNotice("");
    }
  } catch (error) {
    state.likeState.set(post.id, currentLiked ? "liked" : "unliked");
    updatePost(post.id, { liked: currentLiked, stats: oldStats });
    markLocalChange(post.id);
    setNotice(error.message || "操作失败", "error");
  } finally {
    state.pendingLikes.delete(post.id);
    renderFeed();
    renderSelectedIfNeeded(post.id);
  }
}

async function sendComment(post, content) {
  const textValue = text(content).trim();
  if (!textValue) return;
  const postId = post.id;
  const current = currentPostById(postId, post);
  const comments = [...(current.comments || [])];
  const tempId = `pending_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const optimisticComment = {
    id: tempId,
    author: currentLoginAuthor(),
    content: textValue,
    created_at: Math.floor(Date.now() / 1000),
    can_reply: false,
  };
  const oldStats = { ...(current.stats || { likes: 0, comments: 0 }) };
  updatePost(postId, {
    comments: [...comments, optimisticComment],
    stats: { ...oldStats, comments: Number(oldStats.comments || 0) + 1 },
  });
  markLocalChange(postId);
  renderFeed();
  renderSelectedIfNeeded(postId);
  try {
    const data = await apiPost("page/comment", { id: postId, content: textValue });
    const serverComment = data.comment || {};
    const author = mergeAuthor(optimisticComment.author, serverComment.author);
    rememberAuthor(author);
    const target = currentPostById(postId, post);
    const nextComments = [...(target?.comments || [])].map((item) => (
      item.id === tempId
        ? {
          ...item,
          id: serverComment.id || tempId,
          author,
          content: serverComment.content || item.content,
          can_reply: Boolean(serverComment.id),
        }
        : item
    ));
    updatePost(postId, { comments: nextComments });
    markLocalChange(postId);
    setNotice("评论已发送。", "success");
  } catch (error) {
    const target = currentPostById(postId, post);
    const currentComments = [...(target?.comments || [])];
    const hadTemp = currentComments.some((item) => item.id === tempId);
    const currentStats = { ...(target?.stats || oldStats) };
    updatePost(postId, {
      comments: currentComments.filter((item) => item.id !== tempId),
      stats: hadTemp
        ? { ...currentStats, comments: Math.max(0, Number(currentStats.comments || 0) - 1) }
        : currentStats,
    });
    markLocalChange(postId);
    setNotice(error.message || "评论失败", "error");
  } finally {
    renderFeed();
    renderSelectedIfNeeded(postId);
  }
}

async function sendReply(post, comment, content) {
  const replyText = text(content).trim();
  if (!replyText) return false;
  const postId = post.id;
  const pendingKey = `${postId}:${text(comment.id)}`;
  if (state.pendingReplies.has(pendingKey)) return false;
  state.pendingReplies.add(pendingKey);
  const current = currentPostById(postId, post);
  const comments = [...(current.comments || [])];
  const oldStats = { ...(current.stats || { likes: 0, comments: 0 }) };
  const tempId = `pending_reply_${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const targetName = displayAuthorName(comment.author, "评论");
  const previousReplyTarget = state.replyTarget;
  const optimisticReply = {
    id: tempId,
    author: currentLoginAuthor(),
    content: `回复 ${targetName}：${replyText}`,
    created_at: Math.floor(Date.now() / 1000),
    can_reply: false,
  };
  updatePost(postId, {
    comments: [...comments, optimisticReply],
    stats: { ...oldStats, comments: Number(oldStats.comments || 0) + 1 },
  });
  markLocalChange(postId);
  if (state.replyTarget?.postId === postId && state.replyTarget?.commentId === text(comment.id)) {
    state.replyTarget = null;
  }
  renderFeed();
  renderSelectedIfNeeded(postId);
  try {
    const data = await apiPost("page/reply", {
      id: postId,
      commentid: comment.id,
      comment_uin: comment.author?.uin,
      content: replyText,
    });
    const serverReply = data.reply || {};
    const author = mergeAuthor(optimisticReply.author, serverReply.author);
    rememberAuthor(author);
    const target = currentPostById(postId, post);
    const nextComments = [...(target?.comments || [])].map((item) => (
      item.id === tempId
        ? {
          ...item,
          id: serverReply.id || tempId,
          author,
          content: serverReply.content ? `回复 ${targetName}：${serverReply.content}` : item.content,
        }
        : item
    ));
    updatePost(postId, { comments: nextComments });
    markLocalChange(postId);
    setNotice("回复已发送。", "success");
    return true;
  } catch (error) {
    const target = currentPostById(postId, post);
    const currentComments = [...(target?.comments || [])];
    const hadTemp = currentComments.some((item) => item.id === tempId);
    const currentStats = { ...(target?.stats || oldStats) };
    updatePost(postId, {
      comments: currentComments.filter((item) => item.id !== tempId),
      stats: hadTemp
        ? { ...currentStats, comments: Math.max(0, Number(currentStats.comments || 0) - 1) }
        : currentStats,
    });
    markLocalChange(postId);
    state.replyTarget = previousReplyTarget;
    setNotice(error.message || "回复失败", "error");
  } finally {
    state.pendingReplies.delete(pendingKey);
    renderFeed();
    renderSelectedIfNeeded(postId);
  }
  return false;
}

async function deletePost(post) {
  if (!window.confirm("确定删除这条说说吗？")) return;
  try {
    await apiPost("page/delete", { id: post.id });
    state.posts = state.posts.filter((item) => item.id !== post.id);
    state.selected = null;
    el.detailContent.hidden = true;
    el.detailEmpty.hidden = false;
    el.detailPane.classList.remove("has-selection");
    setNotice("说说已删除。", "success");
    renderFeed();
  } catch (error) {
    setNotice(error.message || "删除失败", "error");
  }
}

async function publish(event) {
  event.preventDefault();
  const content = el.publishContent.value;
  if (!content.trim() && !state.media.length) {
    setNotice("写点文字或添加图片再发布。", "warn");
    return;
  }
  el.publishButton.disabled = true;
  const originalText = el.publishButton.textContent;
  el.publishButton.textContent = "发布中...";
  try {
    const data = await apiPost("page/publish", { content, media: state.media });
    el.publishContent.value = "";
    state.media = [];
    renderMedia();
    if (data.post) {
      data.post.author = mergeAuthor(currentLoginAuthor(), data.post.author);
      rememberPostAuthors(data.post);
      state.posts = [data.post, ...state.posts];
      renderFeed();
    } else {
      await loadFeed();
    }
    setNotice("说说已发布。", "success");
  } catch (error) {
    setNotice(error.message || "发布失败", "error");
  } finally {
    el.publishButton.disabled = false;
    el.publishButton.textContent = originalText;
  }
}

async function uploadFiles(files) {
  const maxImages = state.status?.limits?.images || 9;
  for (const file of files) {
    if (state.media.length >= maxImages) {
      setNotice(`最多只能添加 ${maxImages} 张图片。`, "warn");
      break;
    }
    try {
      const result = await withTimeout(
        bridge.upload("page/upload-media", file),
        BRIDGE_REQUEST_TIMEOUT_MS,
        "上传图片超时，请刷新页面后重试。"
      );
      const data = normalizeBridgeResult(result, "上传失败");
      if (!data.media) throw new Error("上传失败");
      state.media.push(data.media);
    } catch (error) {
      setNotice(error.message || "图片上传失败", "error");
    }
  }
  renderMedia();
}

async function openSettings() {
  try {
    const data = await apiGet("page/settings");
    const controls = [];
    el.settingsFields.replaceChildren();
    function render(schema, values, parent, path = []) {
      for (const [key, meta] of Object.entries(schema)) {
        const currentPath = [...path, key];
        if (meta.type === "object") {
          const group = document.createElement("fieldset");
          const legend = document.createElement("legend");
          legend.textContent = meta.description || key;
          group.append(legend);
          if (meta.hint) {
            const hint = document.createElement("p");
            hint.className = "settings-group-hint";
            hint.textContent = meta.hint;
            group.append(hint);
          }
          render(meta.items, values[key] || {}, group, currentPath);
          parent.append(group);
          continue;
        }
        const label = document.createElement("label");
        label.className = "settings-field";
        const title = document.createElement("strong");
        title.textContent = meta.description || key;
        let input;
        if (meta._special === "select_provider") {
          input = document.createElement("input");
          input.setAttribute("list", `settings-providers-${currentPath.join("-")}`);
          input.placeholder = "留空禁用，或选择/输入 Provider ID";
          const suggestions = document.createElement("datalist");
          suggestions.id = `settings-providers-${currentPath.join("-")}`;
          for (const provider of data.providers || []) {
            const option = document.createElement("option");
            option.value = provider.id;
            option.label = provider.model || provider.id;
            suggestions.append(option);
          }
          label.append(suggestions);
        } else if (meta.options) {
          input = document.createElement("select");
          for (const value of meta.options) {
            const option = document.createElement("option");
            option.value = String(value);
            option.textContent = String(value);
            input.append(option);
          }
        } else {
          input = document.createElement(meta.type === "text" || meta.type === "list" ? "textarea" : "input");
          if (meta.type === "bool") input.type = "checkbox";
          else if (meta.type === "int" || meta.type === "float") {
            input.type = "number";
            input.step = meta.type === "int" ? "1" : "any";
            if (meta.slider) {
              input.min = meta.slider.min;
              input.max = meta.slider.max;
            }
          } else if (input.tagName === "TEXTAREA") input.rows = 3;
        }
        if (meta.type === "bool") input.checked = Boolean(values[key]);
        else input.value = meta.type === "list" ? (values[key] || []).join("\n") : String(values[key] ?? "");
        input.dataset.configPath = currentPath.join(".");
        const hint = document.createElement("small");
        hint.textContent = meta.hint || "";
        label.append(title, input, hint);
        parent.append(label);
        controls.push({ input, path: currentPath, type: meta.type });
      }
    }
    render(data.schema, data.values, el.settingsFields);
    el.settingsError.textContent = "";
    el.settingsForm.onsubmit = async (event) => {
      event.preventDefault();
      const values = {};
      for (const { input, path, type } of controls) {
        let target = values;
        for (const key of path.slice(0, -1)) target = target[key] ||= {};
        let value = input.value;
        if (type === "bool") value = input.checked;
        else if (type === "list") value = value.split("\n").map((item) => item.trim()).filter(Boolean);
        else if (type === "int" || type === "float") value = value === "" ? null : Number(value);
        target[path[path.length - 1]] = value;
      }
      try {
        await apiPost("page/settings", { values });
        el.settingsDialog.close();
        await refreshDebugToggle();
        setNotice("配置已保存，请重载插件使所有设置生效。", "success");
      } catch (error) {
        el.settingsError.textContent = error.message || "保存失败";
      }
    };
    el.settingsDialog.showModal();
  } catch (error) {
    setNotice(error.message || "加载配置失败", "error");
  }
}

function bindEvents() {
  el.settingsButton?.addEventListener("click", openSettings);
  el.settingsClose?.addEventListener("click", () => el.settingsDialog.close());
  closeOnBackdrop(el.settingsDialog);
  closeOnBackdrop(el.paletteDialog);
  el.paletteButton?.addEventListener("click", () => el.paletteDialog.showModal());
  el.paletteClose?.addEventListener("click", () => el.paletteDialog.close());
  el.paletteDone?.addEventListener("click", () => el.paletteDialog.close());
  el.paletteReset?.addEventListener("click", () => {
    el.colorOne.value = PALETTE_DEFAULT.one;
    el.colorTwo.value = PALETTE_DEFAULT.two;
    el.gradient.value = PALETTE_DEFAULT.strength;
    updatePalette(true);
  });
  for (const input of [el.colorOne, el.colorTwo, el.gradient]) input?.addEventListener("input", () => updatePalette(true));
  el.sidebarToggle?.addEventListener("click", () => {
    const collapsed = document.querySelector(".shell").classList.toggle("sidebar-collapsed");
    const label = collapsed ? "展开侧栏" : "收起侧栏";
    el.sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    el.sidebarToggle.setAttribute("aria-label", label);
    el.sidebarToggle.title = label;
    el.sidebarToggle.querySelector(".nav-text").textContent = label;
  });
  el.detailClose?.addEventListener("click", closeDetail);
  closeOnBackdrop(el.detailDialog);
  el.targetUin?.addEventListener("input", () => {
    if (state.scope === "friends") renderFeed();
  });
  el.clearTarget?.addEventListener("click", () => {
    el.targetUin.value = "";
    if (state.scope === "profile") {
      closeDetail();
      state.scope = "friends";
      state.targetUin = "";
      state.cursor = "";
      state.posts = [];
      renderTabs();
      loadFeed();
    } else renderFeed();
    el.targetUin.focus();
  });
  for (const button of el.filters) button.addEventListener("click", () => {
    state.feedFilter = button.dataset.filter;
    for (const item of el.filters) item.classList.toggle("active", item === button);
    renderFeed();
  });
  for (const tab of el.tabs) {
    tab.addEventListener("click", async () => {
      state.scope = tab.dataset.scope;
      if (state.scope !== "profile") {
        state.targetUin = "";
        el.targetUin.value = "";
      }
      state.cursor = "";
      state.posts = [];
      state.likeState.clear();
      closeDetail();
      renderTabs();
      await loadFeed();
    });
  }
  el.targetForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.targetUin = el.targetUin.value.trim();
    if (!/^\d+$/.test(state.targetUin)) {
      setNotice("请输入数字 QQ 号后查询空间。", "warn");
      return;
    }
    state.scope = "profile";
    closeDetail();
    state.cursor = "";
    state.posts = [];
    state.likeState.clear();
    renderTabs();
    await loadFeed();
  });
  if (el.accountAvatarBtn && el.accountMenu) {
    const toggleMenu = (event) => {
      event.stopPropagation();
      el.accountMenu.hidden = !el.accountMenu.hidden;
    };
    el.accountMenu.hidden = true;
    el.accountMenu.addEventListener("click", (event) => event.stopPropagation());
    el.accountAvatarBtn.addEventListener("click", toggleMenu);
    el.accountAvatarBtn.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        el.accountMenu.hidden = !el.accountMenu.hidden;
      }
    });
    document.addEventListener("click", (event) => {
      if (!el.accountMenu.hidden
        && !el.accountMenu.contains(event.target)
        && !el.accountAvatarBtn.contains(event.target)) {
        el.accountMenu.hidden = true;
      }
    });
  }
  if (el.themeToggle) {
    el.themeToggle.addEventListener("click", () => {
      const current = document.documentElement.dataset.theme;
      applyTheme(current === "dark" ? "light" : "dark", true);
    });
  }
  if (el.debugToggle) {
    el.debugToggle.addEventListener("click", async () => {
      const on = el.debugToggle.getAttribute("aria-pressed") === "true";
      try {
        await apiGet("page/debug", { enable: on ? "false" : "true" });
      } catch (error) {
        /* 状态以 refreshDebugToggle 返回为准 */
      }
      await refreshDebugToggle();
    });
  }
  el.refreshButton.addEventListener("click", () => {
    state.cursor = "";
    state.posts = [];
    loadFeed();
  });
  el.moreButton.addEventListener("click", () => loadFeed({ append: true }));
  el.publishForm.addEventListener("submit", publish);
  el.mediaInput.addEventListener("change", async () => {
    await uploadFiles(el.mediaInput.files || []);
    el.mediaInput.value = "";
  });
}

async function refreshDebugToggle() {
  if (!el.debugToggle) return;
  try {
    const res = await apiGet("page/debug");
    const on = !!(res && (res.debug ?? (res.data && res.data.debug)));
    const label = el.debugToggle.querySelector("span");
    if (label) label.textContent = on ? "调试日志：开" : "调试日志：关";
    el.debugToggle.setAttribute("aria-pressed", String(on));
  } catch (error) {
    /* 状态读取失败时保持当前显示 */
  }
}

async function init() {
  initializeTheme();
  initializePalette();
  bindEvents();
  await refreshDebugToggle();
  if (!bridge) {
    setNotice("没有检测到 AstrBot Pages bridge，请从 AstrBot WebUI 插件页面进入。", "error");
    return;
  }
  
  try {
    state.context = await withTimeout(
      bridge.ready(),
      BRIDGE_READY_TIMEOUT_MS,
      "初始化 AstrBot WebUI 桥接超时，请刷新页面后重试。"
    );
  } catch (error) {
    setNotice(error.message || "桥接初始化失败", "error");
    return;
  }

  renderTabs();
  
  try {
    await loadAccounts();
    await loadStatus();
    await loadFeed();
  } catch (error) {
    setNotice(error.message || "初始化失败", "error");
  }
}

init();
