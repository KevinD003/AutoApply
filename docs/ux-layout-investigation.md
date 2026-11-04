# UX layout investigation — navigation & layout defects (Slice A)

Status: complete. Method and verdicts below; a maintained regression guard
(`frontend/e2e/layout-regression.spec.ts`) encodes the invariants this investigation
established, so the conclusions cannot silently regress.

## Why this exists

Earlier screenshots suggested three navigation/layout problems:

1. the mobile bottom navigation appeared to cross over the "Import CSV / XLSX" card;
2. the top header appeared to sit **mid-page** on the Profile screen;
3. the desktop **List / Swipe** control looked faint.

Those screenshots were **stitched full-page captures** (`screenshot({ fullPage: true })`).
A full-page capture renders a tall image by compositing the page at several scroll
offsets. A `position: sticky` or `position: fixed` element (our top header and bottom
nav) is painted **once per stitch band**, so it can appear repeated or parked at a
mid-page offset that never occurs in a real viewport. That is a property of the capture
tool, not of the running app.

## Method

The app was driven in a real browser (Playwright, the project's e2e harness) at the two
project viewports — desktop `1280×800` and mobile `390×844` — with a synthetic account and
synthetic jobs. Screenshots were taken as **ordinary viewport captures** (never
`fullPage`) at the top, middle and bottom scroll positions of each page, plus the swipe
deck. No production layout was changed to make any capture tool look correct.

## Verdicts

| # | Reported symptom | Verdict | Evidence (viewport capture) |
|---|---|---|---|
| 1 | Bottom nav crosses the Import card (mobile) | **Full-page artifact.** The bottom nav is a normal fixed bar; content scrolls under it, and because `<main>` carries `pb-28` on mobile the last job clears it with margin. No content is permanently obscured. | `mobile-jobs-list` top/middle/bottom |
| 2 | Header appears mid-page (Profile) | **Full-page artifact.** The `<header>` (`sticky top-0`) stays pinned at the top of the viewport at every scroll position on both viewports. The frosted glass shows a faint bleed of the content scrolling beneath it (the intended liquid-glass effect); a stitched capture misreads that as a second, mid-page header. | `mobile-profile` / `desktop-profile` middle |
| 3 | Faint desktop List / Swipe control | **Minor, real — prominence, not a defect.** The control is legible and functional but understated (a small muted pill, top-right). It is not a correctness/overlap defect. Making it a prominent, primary control is part of the Jobs-first restructure (Slice B), not a nav fix. | `desktop-jobs-list` top |

Additional checks requested (overlap, stacking context, sticky position):

- **No horizontal overflow** at mobile width on Jobs or Profile.
- **No stacking-context trap:** header `z-30`, bottom nav `z-40`, modal sheet `z-60`;
  nothing interactive is covered.
- **Swipe controls reachable on mobile:** the always-present Pass / Undo / Apply buttons
  sit above the fixed bottom nav, not behind it.

## What is actually wrong (handled in later slices, not here)

The real, visible problems are **information architecture**, not navigation defects:

- **Jobs leads with admin forms.** The first viewport (desktop and mobile) is the
  "Add a job" and "Import CSV / XLSX" forms; the jobs themselves are below the fold.
  → Slice B (Jobs-first: heading → search/filters + prominent List/Swipe → jobs/swipe →
  secondary Add/Import in sheets).
- **Profile and Account are walls of always-expanded forms.** Every section renders its
  full add/edit form at once (e.g. the whole "Add position" form under an empty Work
  history). → Slice C.

## Production change in this slice

**None.** Changing the sticky/fixed navigation to flatter a full-page screenshot tool
would be the wrong fix (the running app is correct). This slice delivers the investigation
and a maintained guard asserting the invariants above, so a future change cannot
reintroduce a real overlap, an unpinned header, or horizontal overflow without a test
failing.
