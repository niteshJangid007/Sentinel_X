/* Registers the service worker so the dashboard can be installed as an app. */
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* Installation is optional; the dashboard still works normally. */
    });
  });
}
