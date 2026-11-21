// Runs in the page's own world so it can see LeetCode's fetch/XHR responses.
// Watches only the submission verdict poll (/submissions/detail/<numeric id>/check/);
// "Run" uses runcode_* ids and is ignored. Sends a bare signal, never the code
// or the verdict: the lock re-checks LeetCode itself, so the signal is not trusted.
(() => {
  const CHECK = /\/submissions\/detail\/\d+\/check\/?/;
  // Any verdict poll, Run included. Only logged: a "Run" proves interception
  // works on the live site (DevTools console) without minting a credit.
  const ANY_CHECK = /\/submissions\/detail\/[^/]+\/check\/?/;
  const announce = (body) => {
    // status_code 10 is Accepted (leetcode.el's table); either field suffices.
    const accepted = body && (body.status_msg === "Accepted" || body.status_code === 10);
    if (accepted && body.state === "SUCCESS") {
      window.postMessage({ source: "leetcode-guard", type: "accepted" }, "*");
    }
  };
  const inspect = (url, text) => {
    if (!ANY_CHECK.test(url)) return;
    let body;
    try { body = JSON.parse(text); } catch (_) { return; /* not JSON: not a verdict */ }
    console.debug("[leetcode-guard] verdict poll", url, body && body.state, body && body.status_msg);
    if (CHECK.test(url)) announce(body);
  };

  const realFetch = window.fetch;
  window.fetch = async function (...args) {
    const response = await realFetch.apply(this, args);
    const url = response.url || String(args[0] && args[0].url ? args[0].url : args[0]);
    if (ANY_CHECK.test(url)) response.clone().text().then((t) => inspect(url, t), () => {});
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
