# Optional manual check: how the posting's dropdowns behave

**Optional.** Use your own normal browser, the way you would read any job posting. This
does not authorize any automation against the page; nothing in NoEfforts runs because of it.

**Do not:**
- enter any personal information;
- choose an answer you would not want kept: if a choice sticks, reload the page;
- submit anything.

**Please do not share:**
- page source, screenshots or recordings;
- the employer, the job title or the link;
- question or option wording;
- cookies, sign-ins or network logs.

The answers below are all that is needed.

## Questions (answer for one or two dropdowns)

1. **Does a single click on the dropdown visibly open a menu?**
   yes / no / only when clicking a small arrow beside it / only with the keyboard
   (for example the down-arrow key)
2. **Does typing into it filter the options?** yes / no / did not try
3. **How quickly does the menu appear?** immediately / after a noticeable delay
4. **What does it look like?**
   - a list attached below the field (popup);
   - a separate box or overlay (dialog);
   - a list that pushes the page content down (inline);
   - something else.
5. **Roughly how many options does it show?** a few (under 10) / dozens / hundreds
6. *(Only if you choose to open your browser's network panel.)* **Do requests whose
   address contains `/locales/` and ends in `.json` load successfully?**
   yes / no / did not check
7. **Does the list show all its options at once?** all at once / loads more as you scroll /
   needs typing to find options
8. **For each of these required controls — (a) the control beside the phone number and
   (b) the other unlabelled-looking control — what kind of choice is it?** For each, answer:
   country or dialling code / yes-no / list of places / something else. Give the kind only,
   not its wording.

Reply with the question numbers and the short answers only.

**How the answers are kept** (`providers/path_a.py`): only as the fixed choices above, in
`docs/evidence/path-a.json`, with the date and "owner_manual_observation" as their source.
Anything else (wording, names, links, free text) is refused. The answers are advisory: they
say which bounded strategy a local fixture would have to prove next, and they never change a
capability, a route or an approval on their own.
