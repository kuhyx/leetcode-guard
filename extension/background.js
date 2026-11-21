// Rings the lock's loopback doorbell. host_permissions exempts this request from
// CORS / Private Network Access. No lock running means the port is closed and the
// request fails; that is the normal state and is ignored.
const NUDGE_URL = "http://127.0.0.1:8772/nudge";
// The guard's heartbeat listener; same exemption, same "closed port is normal".
// Its own line so scripts/verify_heartbeat_extension.py can swap the port.
const BEAT_URL = "http://127.0.0.1:8782/beat";

chrome.runtime.onMessage.addListener((message) => {
  if (!message) return;
  if (message.type === "accepted") {
    fetch(NUDGE_URL, { method: "POST" }).catch(() => {});
  } else if (message.type === "beat") {
    // Exactly {slug, tab}: no title, code, URL or timestamp (the server keeps time).
    const body = JSON.stringify({ slug: message.slug, tab: message.tab });
    fetch(BEAT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    }).catch(() => {});
  }
});
