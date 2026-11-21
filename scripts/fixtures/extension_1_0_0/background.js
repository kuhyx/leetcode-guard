// Rings the lock's loopback doorbell. host_permissions exempts this request from
// CORS / Private Network Access. No lock running means the port is closed and the
// request fails; that is the normal state and is ignored.
const NUDGE_URL = "http://127.0.0.1:8772/nudge";

chrome.runtime.onMessage.addListener((message) => {
  if (message && message.type === "accepted") {
    fetch(NUDGE_URL, { method: "POST" }).catch(() => {});
  }
});
