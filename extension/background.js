// The background worker completes a save even if the popup closes first (D90). It acts only on
// a message from this extension's own pages, and only for a tab it reads itself: its address
// and title, never its content.
import { saveJob } from "./lib.js";

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id || !message || message.type !== "save") return false;
  (async () => {
    let tab;
    try {
      tab = await chrome.tabs.get(Number(message.tabId));
    } catch {
      reply({ ok: false, message: "That tab is gone." });
      return;
    }
    const settings = await chrome.storage.local.get(["base", "token"]);
    reply(await saveJob(settings, tab));
  })();
  return true; // the reply is asynchronous
});
