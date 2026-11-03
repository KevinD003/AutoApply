"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { cx } from "./cx";
import { IconButton } from "./primitives";
import { IconCheck, IconUndo, IconX } from "./icons";
import { useSwipe } from "./useSwipe";

/*
  Swipe discovery deck. Parent owns the card list and removes a card when onDecide
  fires. Right = "apply" (an intent to prepare — NOT an application), left = "pass".
  Swipe is an enhancement over always-present, fully-labelled buttons and arrow-key
  support, so the deck is completely usable without touch and by screen readers.
  Honours reduced-motion (no fly-off animation; the decision is immediate).
*/

function prefersReduced() {
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

function clamp(n, lo, hi) {
  return Math.max(lo, Math.min(hi, n));
}

export function SwipeDeck({
  cards = [],
  renderCard,
  onDecide,
  onUndo,
  canUndo = false,
  applyLabel = "Apply",
  passLabel = "Pass",
  emptyState = null,
}) {
  const [leaving, setLeaving] = useState(null); // { id, dir }
  const finalizedRef = useRef(false);
  const timerRef = useRef(null);
  const top = cards[0] ?? null;

  const finalize = useCallback(
    (card, dir) => {
      if (finalizedRef.current || !card) return;
      finalizedRef.current = true;
      clearTimeout(timerRef.current);
      setLeaving(null);
      onDecide?.(card, dir);
    },
    [onDecide],
  );

  const commit = useCallback(
    (dir) => {
      if (!top || leaving) return;
      const card = top;
      finalizedRef.current = false;
      setLeaving({ id: card.id, dir });
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => finalize(card, dir), prefersReduced() ? 0 : 340);
    },
    [top, leaving, finalize],
  );

  const { delta, dragging, bind, reset } = useSwipe({ onCommit: commit, enabled: !!top && !leaving });

  useEffect(() => () => clearTimeout(timerRef.current), []);

  const onKeyDown = useCallback(
    (e) => {
      if (e.key === "ArrowRight") {
        e.preventDefault();
        commit("apply");
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        commit("pass");
      } else if ((e.key === "Backspace" || e.key === "z") && canUndo) {
        e.preventDefault();
        onUndo?.();
        reset();
      }
    },
    [commit, onUndo, canUndo, reset],
  );

  if (!top) {
    return <div>{emptyState}</div>;
  }

  const applyOpacity = leaving?.dir === "apply" ? 1 : clamp(delta.x / 110, 0, 1);
  const passOpacity = leaving?.dir === "pass" ? 1 : clamp(-delta.x / 110, 0, 1);

  return (
    <div className="mx-auto w-full max-w-md">
      <div
        className="relative h-[clamp(420px,62vh,560px)] select-none"
        role="group"
        aria-roledescription="Swipeable job deck"
        aria-label="Job discovery deck. Use the Pass and Apply buttons, or the left and right arrow keys."
        tabIndex={0}
        onKeyDown={onKeyDown}
      >
        {cards.slice(0, 3).map((card, i) => {
          const isTop = i === 0;
          const isLeaving = leaving && leaving.id === card.id;
          let transform;
          let transition;
          if (isTop) {
            if (isLeaving) {
              const sign = leaving.dir === "apply" ? 1 : -1;
              transform = `translateX(${sign * 130}%) rotate(${sign * 14}deg)`;
              transition = "transform var(--dur-slow) var(--ease), opacity var(--dur-slow) var(--ease)";
            } else if (dragging) {
              transform = `translate(${delta.x}px, ${delta.y * 0.3}px) rotate(${delta.x * 0.04}deg)`;
              transition = "none";
            } else {
              transform = "translate(0,0)";
              transition = "transform var(--dur) var(--ease)";
            }
          } else {
            transform = `translateY(${i * 12}px) scale(${1 - i * 0.04})`;
            transition = "transform var(--dur) var(--ease)";
          }
          return (
            <article
              key={card.id}
              {...(isTop ? bind : {})}
              onTransitionEnd={
                isTop
                  ? (e) => {
                      if (e.propertyName === "transform" && leaving && leaving.id === card.id) {
                        finalize(card, leaving.dir);
                      }
                    }
                  : undefined
              }
              aria-hidden={isTop ? undefined : true}
              className={cx(
                "absolute inset-0 overflow-hidden rounded-[var(--r-xl)] border border-hairline bg-surface shadow-[var(--shadow-lg)]",
                isTop ? "cursor-grab touch-pan-y active:cursor-grabbing" : "pointer-events-none",
                isLeaving && "opacity-0",
              )}
              style={{ transform, transition, zIndex: cards.length - i }}
            >
              {/* Intent overlays on the top card. */}
              {isTop && (
                <>
                  <span
                    aria-hidden="true"
                    style={{ opacity: applyOpacity, transform: `rotate(-10deg) scale(${0.82 + 0.18 * applyOpacity})` }}
                    className="absolute left-5 top-5 z-10 rounded-[var(--r-md)] border-2 border-positive bg-positive-weak px-3 py-1 text-lg font-extrabold uppercase tracking-wider text-positive-ink"
                  >
                    {applyLabel}
                  </span>
                  <span
                    aria-hidden="true"
                    style={{ opacity: passOpacity, transform: `rotate(10deg) scale(${0.82 + 0.18 * passOpacity})` }}
                    className="absolute right-5 top-5 z-10 rounded-[var(--r-md)] border-2 border-ink-faint bg-surface-3 px-3 py-1 text-lg font-extrabold uppercase tracking-wider text-ink-muted"
                  >
                    {passLabel}
                  </span>
                </>
              )}
              <div className="h-full">{renderCard(card)}</div>
            </article>
          );
        })}
      </div>

      {/* Always-present, labelled controls (the accessible path). */}
      <div className="mt-5 flex items-center justify-center gap-5">
        <IconButton label={`${passLabel} this job`} tone="neutral" onClick={() => commit("pass")}>
          <IconX size={24} />
        </IconButton>
        <IconButton
          label="Undo the last decision"
          tone="brand"
          className="h-11 w-11 opacity-100 disabled:opacity-40"
          onClick={() => {
            onUndo?.();
            reset();
          }}
          disabled={!canUndo}
        >
          <IconUndo size={18} />
        </IconButton>
        <IconButton label={`${applyLabel} to this job`} tone="positive" onClick={() => commit("apply")}>
          <IconCheck size={26} />
        </IconButton>
      </div>
    </div>
  );
}
