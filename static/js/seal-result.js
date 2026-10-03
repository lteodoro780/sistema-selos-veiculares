"use strict";
(() => {
  function stale() {
    document.getElementById("result-live").hidden = true;
    document.getElementById("result-stale").hidden = false;
  }
  const deadline = Date.now() + 60000;
  setTimeout(stale, 60000);
  window.addEventListener("offline", stale);
  window.addEventListener("pageshow", event => { if (event.persisted) stale(); });
  document.addEventListener("visibilitychange", () => { if (!document.hidden && Date.now() >= deadline) stale(); });
})();
