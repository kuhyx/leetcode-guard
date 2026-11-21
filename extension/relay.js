// Isolated world: the only side that may talk to the extension's service worker.
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (data && data.source === "leetcode-guard" && data.type === "accepted") {
    chrome.runtime.sendMessage({ type: "accepted" });
  }
});

// Heartbeat: tells the guard which problem page is open so it can time solving.
// Only the slug and the tab leave this file; never the title, code or URL.
// Own line, so scripts/verify_heartbeat_extension.py can shorten the minute.
const BEAT_INTERVAL_MS = 60000;
const ROUTE_POLL_MS = 1000;
const TABS = ["editorial", "solutions", "submissions"];

// "/problems/<slug>/<tab>/..." -> { slug, tab }, or null off a problem page.
// Anything but the three named tabs (the bare problem page too) is "description".
const parseProblem = (pathname) => {
  const match = /^\/problems\/([a-z0-9-]+)(?:\/([^/]*))?/.exec(pathname);
  if (!match) return null;
  return { slug: match[1], tab: TABS.includes(match[2]) ? match[2] : "description" };
};

const beat = () => {
  if (document.visibilityState !== "visible") return;
  const problem = parseProblem(location.pathname);
  if (problem) chrome.runtime.sendMessage({ type: "beat", ...problem });
};

// LeetCode is a single-page app: a tab switch is history.pushState, with no
// load and no event this isolated world can hear, so the path is polled.
let lastPath = location.pathname;
setInterval(() => {
  if (location.pathname === lastPath) return;
  lastPath = location.pathname;
  beat();
}, ROUTE_POLL_MS);
setInterval(beat, BEAT_INTERVAL_MS);
document.addEventListener("visibilitychange", beat);
beat();
