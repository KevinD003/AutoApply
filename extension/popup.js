import { checkTab } from "./lib.js";

const result = document.getElementById("result");

function show(text, link) {
  result.textContent = text;
  if (link) {
    const a = document.createElement("a");
    a.href = link;
    a.target = "_blank";
    a.rel = "noreferrer";
    a.textContent = " Open it";
    result.append(a);
  }
}

document.getElementById("save").addEventListener("click", async () => {
  // The tab the popup was opened on: its address and title are all the extension reads.
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const job = checkTab(tab);
  if (job instanceof Error) return show(job.message);
  show("Saving…");
  let out;
  try {
    out = await chrome.runtime.sendMessage({ type: "save", tabId: tab.id });
  } catch {
    out = undefined;
  }
  // The worker may have sent the request before failing to answer: say so. Saving again is safe
  // (a job already in NoEfforts is not added twice).
  if (!out) return show("No answer, so it is not known whether the job was saved. Saving again is safe.");
  show(out.message, out.ok ? out.jobUrl : undefined);
});
