"use client";

import { useCallback, useRef, useState } from "react";

/*
  Pointer-drag math for one swipe card, built so the gesture never fights the rest of the
  card. Two guards make it feel right:

  1. Interactive opt-out: a pointer-down that lands on a link, button, form control or an
     element marked [data-noswipe] (e.g. a scrollable description, a "read more" toggle) is
     left alone, so those work with a normal tap/scroll.
  2. Axis lock: the swipe only engages once the gesture is clearly horizontal. If the first
     movement is vertical it bows out entirely, so vertical scrolling of a long card is
     native and smooth. Paired with `touch-action: pan-y` on the card, a horizontal drag is
     never consumed by the scroller and a vertical drag is never consumed by the swipe.

  On release, onCommit("apply"|"pass") fires when the horizontal threshold or a fast flick is
  crossed; otherwise it snaps back. It does not animate — the deck owns that.
*/

const INTERACTIVE = "a,button,input,textarea,select,label,[role='button'],[data-noswipe]";
const DECIDE_PX = 8; // movement needed before we decide the axis

export function useSwipe({ onCommit, threshold = 110, enabled = true } = {}) {
  const [delta, setDelta] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const start = useRef(null); // { x, y, t, axis: null | "x" | "y" }

  const reset = useCallback(() => {
    start.current = null;
    setDragging(false);
    setDelta({ x: 0, y: 0 });
  }, []);

  const onPointerDown = useCallback(
    (e) => {
      if (!enabled) return;
      if (e.pointerType === "mouse" && e.button !== 0) return; // left button only
      if (e.target?.closest?.(INTERACTIVE)) return; // let controls/scrollers handle it
      start.current = { x: e.clientX, y: e.clientY, t: e.timeStamp, axis: null };
      // Capture is deferred until the gesture is known to be horizontal (below), so a
      // vertical scroll is never stolen from the browser.
    },
    [enabled],
  );

  const onPointerMove = useCallback((e) => {
    const s = start.current;
    if (!s) return;
    const dx = e.clientX - s.x;
    const dy = e.clientY - s.y;
    if (s.axis === null) {
      const ax = Math.abs(dx);
      const ay = Math.abs(dy);
      if (ax < DECIDE_PX && ay < DECIDE_PX) return; // too small to tell yet
      if (ay > ax) {
        start.current = null; // vertical: this is a scroll — leave it to the browser
        return;
      }
      s.axis = "x";
      setDragging(true);
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    }
    if (s.axis === "x") setDelta({ x: dx, y: dy });
  }, []);

  const onPointerUp = useCallback(
    (e) => {
      const s = start.current;
      if (!s) return;
      if (s.axis !== "x") {
        start.current = null; // never engaged as a swipe (a tap or a vertical scroll)
        return;
      }
      const dx = e.clientX - s.x;
      const dt = Math.max(1, e.timeStamp - s.t);
      const velocity = dx / dt; // px/ms
      const far = Math.abs(dx) > threshold;
      const flick = Math.abs(velocity) > 0.6 && Math.abs(dx) > 40;
      try {
        e.currentTarget.releasePointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
      if (far || flick) {
        const dir = dx > 0 ? "apply" : "pass";
        setDragging(false);
        start.current = null;
        onCommit?.(dir);
      } else {
        reset();
      }
    },
    [onCommit, reset, threshold],
  );

  return {
    delta,
    dragging,
    reset,
    bind: { onPointerDown, onPointerMove, onPointerUp, onPointerCancel: reset },
  };
}
