// Isolated world: the only side that may talk to the extension's service worker.
window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  const data = event.data;
  if (data && data.source === "leetcode-guard" && data.type === "accepted") {
    chrome.runtime.sendMessage({ type: "accepted" });
  }
});
