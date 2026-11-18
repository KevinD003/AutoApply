// D169, D170: what the account's standing rule does with an application paused on a changed form (the server's `verdict`), in the
// words the Questions page and the application's page both show. D132's own words (and their "apply on the employer's site") only
// when the application is yours; while the rule may still send it, how to take it over instead.

export const RULE_CONTINUES =
  "Your automatic applying continues it by itself: it reads the form again, or tries this version once more (the page is checked again " +
  "before anything is entered); a new question, if the form now has one, waits for your answer under Questions. Do not apply on the " +
  "employer's site meanwhile.";

export const TAKE_OVER =
  "If you apply on the employer's site yourself instead, first choose “I applied myself” for it in the Tracker, so it is never sent twice.";

// D171: what it waits for besides, while the recorded permission does not cover submitting (the server's `rule_step4`).
export const STEP4 = " and your recorded permission covers submitting (step 4)";

export const RULE_WAITS = {
  stopped: (s) => `Your automatic applying is stopped now (the Tracker shows why); when it runs again${s}, it continues this application by itself.`,
  declined: (s) =>
    "Your automatic applying does not continue it while this job's signals or your preferences rule it out (the job's page says why); if " +
    `that changes${s}, it continues it by itself.`,
  unreadable: (s) =>
    `Your automatic applying could not read the employer's page again (it tries once a day); once it can${s}, it continues this application ` +
    "by itself.",
  questions: (s) => `Your automatic applying tries this version once more by itself as soon as you answer the open questions under Questions${s}.`,
  // D171: a recorded permission for rehearsals only.
  submit_not_permitted: () =>
    "This employer's rehearsal held, and your recorded permission does not cover submitting (step 4): once it does, your " +
    "automatic applying continues this application by itself.",
};

// D171: an application the rule held for step 4, with no pause: what it does with it (its page's notice).
export const HELD_CONTINUES =
  "Your automatic applying submits this application by itself now that your recorded permission covers submitting (step 4); it " +
  "rehearses again first if this employer's rehearsal no longer counts. Do not apply on the employer's site meanwhile.";

// After D132's own "or apply on the employer's site": record it, so it is never sent twice.
export const APPLIED_YOURSELF = "and then choose “I applied myself” for it in the Tracker";

export function waitsWords(why, step4 = false) {
  return `${(RULE_WAITS[why] ?? RULE_WAITS.stopped)(step4 ? STEP4 : "")} ${TAKE_OVER}`;
}

export function heldWords(rule, why, step4 = false) {
  if (rule === "continues") return HELD_CONTINUES;
  if (why === "questions")
    return `Your automatic applying goes on with it by itself as soon as you answer the open questions under Questions${step4 ? STEP4 : ""}. ${TAKE_OVER}`;
  return waitsWords(why, step4);
}
