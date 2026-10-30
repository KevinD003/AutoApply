import { DEFAULT_BASE, checkBase, checkToken } from "./lib.js";

const base = document.getElementById("base");
const token = document.getElementById("token");
const state = document.getElementById("token-state");
const status = document.getElementById("status");

async function load() {
  const s = await chrome.storage.local.get(["base", "token"]);
  base.value = s.base || DEFAULT_BASE;
  token.value = ""; // a saved token is never shown again
  state.textContent = s.token ? "A token is saved." : "No token saved yet.";
}

document.getElementById("save").addEventListener("click", async () => {
  const origin = checkBase(base.value);
  if (origin instanceof Error) {
    status.textContent = origin.message;
    return;
  }
  const update = { base: origin };
  const t = token.value.trim();
  const saved = await chrome.storage.local.get(["base", "token"]);
  if (!t && saved.token && saved.base !== origin) {
    // A token checked against one address is never sent to another.
    await chrome.storage.local.remove("token");
    await chrome.storage.local.set(update);
    status.textContent = "Saved. The address changed, so the token was removed: add it again.";
    await load();
    return;
  }
  if (t) {
    if (!/^ne_[A-Za-z0-9_-]{8,200}$/.test(t)) {
      status.textContent = "That does not look like a NoEfforts token (it starts with ne_).";
      return;
    }
    status.textContent = "Checking the token…";
    const refused = await checkToken(origin, t);
    if (refused) {
      status.textContent = `Not saved. ${refused}`;
      return;
    }
    update.token = t;
  }
  await chrome.storage.local.set(update);
  status.textContent = "Saved.";
  await load();
});

document.getElementById("forget").addEventListener("click", async () => {
  await chrome.storage.local.remove("token");
  status.textContent = "The token was removed from this browser.";
  await load();
});

load();
