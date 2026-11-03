"use client";

/*
  The NoEfforts motion system (D125). One coherent toolkit, transform/opacity only, no
  animation dependency. Every piece degrades to an instant, non-animated form under
  `prefers-reduced-motion` (the CSS in globals.css collapses the durations; the hook lets
  JS-driven pieces skip entirely). Motion is used to explain relationships and outcomes —
  entrances, expand/collapse, sheets, loading→content — never to delay content, block input,
  move text under the reader, or imply success before it is confirmed.
*/

import { Children, cloneElement, isValidElement, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { cx } from "./cx";

/* SSR-safe read of the user's reduced-motion preference. Defaults to "motion on" on the
   server and the first client paint, then corrects — so nothing depends on it to render. */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(!!mq.matches);
    update();
    mq.addEventListener?.("change", update);
    return () => mq.removeEventListener?.("change", update);
  }, []);
  return reduced;
}

const REVEAL = { rise: "animate-rise", fade: "animate-fade", scale: "animate-scale-in", pop: "animate-pop" };

/* A one-shot entrance for a block of content. Content is present immediately; only opacity
   and transform animate, so nothing is delayed or hidden. */
export function Reveal({ as: Tag = "div", variant = "rise", className, children, ...rest }) {
  return (
    <Tag className={cx(REVEAL[variant] || REVEAL.rise, className)} {...rest}>
      {children}
    </Tag>
  );
}

/* Children enter in a short, bounded sequence (a list settling into place). The per-item
   delay is capped so a long list never makes the reader wait. */
export function Stagger({ as: Tag = "div", className, children, max = 10, ...rest }) {
  let i = -1;
  return (
    <Tag className={cx("ne-stagger", className)} {...rest}>
      {Children.map(children, (child) => {
        if (!isValidElement(child)) return child;
        i += 1;
        return cloneElement(child, {
          style: { ...(child.props.style || {}), "--i": Math.min(i, max) },
        });
      })}
    </Tag>
  );
}

/* Expand/collapse that animates real height via grid-template-rows (0fr→1fr): smooth, no
   measured max-height guesswork, and the reduced-motion rule makes it instant. Content is
   kept mounted so focus and form state survive a collapse. */
export function Collapse({ open, children, className, durMs = 320, id }) {
  return (
    <div
      id={id}
      className={cx("grid", className)}
      style={{
        gridTemplateRows: open ? "1fr" : "0fr",
        transition: `grid-template-rows ${durMs}ms var(--ease-standard)`,
      }}
      aria-hidden={open ? undefined : true}
    >
      <div className="min-h-0 overflow-hidden">{children}</div>
    </div>
  );
}

/* A replayed, subtle entrance on route change: keyed on the pathname so each navigation
   remounts the wrapper and the page rises in. Never blocks: the page is rendered at once. */
export function RouteTransition({ children, className }) {
  const pathname = usePathname();
  return (
    <div key={pathname} className={cx("animate-rise", className)}>
      {children}
    </div>
  );
}

/*
  An accessible modal surface: a bottom sheet on phones, a centred dialog on wider screens.
  Scrim, Escape, body-scroll lock, focus into the panel and back to the opener on close,
  safe-area padding, opaque glass fallback. Animations are neutralised under reduced motion.
  Urgent content is never hidden behind it — callers keep errors inline.
*/
export function Sheet({ open, onClose, title, labelledBy, children, className }) {
  const panel = useRef(null);
  const opener = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    opener.current = document.activeElement;
    panel.current?.focus();
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose?.();
      }
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center sm:items-center" role="presentation">
      <button
        type="button"
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-black/40 animate-fade"
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label={labelledBy ? undefined : title}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={cx(
          "glass-strong relative w-full max-h-[92vh] overflow-y-auto rounded-t-[var(--r-xl)]",
          "border border-hairline pb-safe shadow-[var(--shadow-lg)] outline-none animate-sheet-up",
          "sm:w-[min(640px,92vw)] sm:max-h-[86vh] sm:rounded-[var(--r-xl)] sm:animate-scale-in",
          className,
        )}
      >
        {children}
      </div>
    </div>
  );
}
