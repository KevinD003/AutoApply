"use client";

import { useCallback, useRef, useState } from "react";

/*
  Pointer-drag math for one swipe card. Framework-agnostic enough to unit-test:
  it tracks the horizontal/vertical delta during a pointer drag and, on release,
  calls onCommit("apply"|"pass") when the horizontal threshold (or a fast flick)
  is crossed, otherwise snaps back. It does not animate — the deck owns that.
*/
export function useSwipe({ onCommit, threshold = 110, enabled = true } = {}) {
  const [delta, setDelta] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const start = useRef(null);

  const reset = useCallback(() => {
    start.current = null;
    setDragging(false);
    setDelta({ x: 0, y: 0 });
  }, []);

  const onPointerDown = useCallback(
    (e) => {
      if (!enabled) return;
      start.current = { x: e.clientX, y: e.clientY, t: e.timeStamp };
      setDragging(true);
      try {
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        /* ignore */
      }
    },
    [enabled],
  );

  const onPointerMove = useCallback((e) => {
    if (!start.current) return;
    setDelta({ x: e.clientX - start.current.x, y: e.clientY - start.current.y });
  }, []);

  const onPointerUp = useCallback(
    (e) => {
      if (!start.current) return;
      const dx = e.clientX - start.current.x;
      const dt = Math.max(1, e.timeStamp - start.current.t);
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
