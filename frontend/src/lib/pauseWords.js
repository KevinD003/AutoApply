// D169, D170: what the account's standing rule does with an application paused on a changed form (the server's `verdict`), in the
// words the Questions page and the application's page both show. D132's own words (and their "apply on the employer's site") only
// when the application is yours; while the rule may still send it, how to take it over instead.

export const RULE_CONTINUES =
  "Your automatic applying continues it by itself: it reads the form again, or tries this version once more (the page is checked again " +
  "before anything is entered); a new question, if the form now has one, waits for your answer under Questions. Do not apply on the " +
  "employer's site meanwhile.";

export const TAKE_OVER =
  "If you apply on the employer's site yourself instead, first choose “I applied myself” for it in the Tracker, so it is never sent twice.";

export const RULE_WAITS = {
  stopped: "Your automatic applying is stopped now (the Tracker shows why); when it runs again, it continues this application by itself.",
  declined:
    "Your automatic applying does not continue it while this job's signals or your preferences rule it out (the job's page says why); if " +
    "that changes, it continues it by itself.",
  unreadable:
    "Your automatic applying could not read the employer's page again (it tries once a day); once it can, it continues this application " +
    "by itself.",
  questions: "Your automatic applying tries this version once more by itself as soon as you answer the open questions under Questions.",
};

// After D132's own "or apply on the employer's site": record it, so it is never sent twice.
export const APPLIED_YOURSELF = "and then choose “I applied myself” for it in the Tracker";

export function waitsWords(why) {
  return `${RULE_WAITS[why] ?? RULE_WAITS.stopped} ${TAKE_OVER}`;
}
