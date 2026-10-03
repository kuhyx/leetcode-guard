// Runs in the page's own world so it can see LeetCode's fetch/XHR responses.
// Watches only the submission verdict poll (/submissions/detail/<numeric id>/check/);
// "Run" uses runcode_* ids and is ignored. Sends a bare signal, never the code
// or the verdict: the lock re-checks LeetCode itself, so the signal is not trusted.
(() => {
  const CHECK = /\/submissions\/detail\/\d+\/check\/?/;
  const announce = (body) => {
    // status_code 10 is Accepted (leetcode.el's table); either field suffices.
    const accepted = body && (body.status_msg === "Accepted" || body.status_code === 10);
    if (accepted && body.state === "SUCCESS") {
      window.postMessage({ source: "leetcode-guard", type: "accepted" }, "*");
    }
  };
  const inspect = (url, text) => {
    if (!CHECK.test(url)) return;
    try { announce(JSON.parse(text)); } catch (_) { /* not JSON: not a verdict */ }
  };

  const realFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await realFetch.apply(this, args);
    const url = response.url || String(args[0] && args[0].url ? args[0].url : args[0]);
    if (CHECK.test(url)) response.clone().text().then((t) => inspect(url, t), () => {});
    return response;
  };

  const realOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this.addEventListener("load", () => {
      try { inspect(String(url), this.responseText); } catch (_) { /* binary body */ }
    });
    return realOpen.call(this, method, url, ...rest);
  };
})();
