"use client";

import { cloneElement, isValidElement, useId } from "react";

import { cx } from "./cx";

/*
  NoEfforts premium primitives (.jsx). Styled entirely with the semantic token
  utilities from globals.css, so every component follows light/dark automatically
  with no `dark:` variants. Touch targets are >=44px. Nothing here is imported by
  the existing .tsx pages, so adding this kit changes no current screen.
*/

const TONE = {
  brand: "bg-brand-weak text-brand",
  positive: "bg-positive-weak text-positive-ink",
  caution: "bg-caution-weak text-caution-ink",
  danger: "bg-danger-weak text-danger-ink",
  info: "bg-info-weak text-info-ink",
  neutral: "bg-surface-3 text-ink-muted",
};

/** A plain elevated panel. */
export function Surface({ as: As = "div", className, children, ...props }) {
  return (
    <As
      className={cx("rounded-[var(--r-lg)] bg-surface shadow-[var(--shadow-sm)]", className)}
      {...props}
    >
      {children}
    </As>
  );
}

/** A content card with optional title + actions row. */
export function Card({ title, subtitle, actions, className, children, ...props }) {
  return (
    <section
      className={cx(
        "rounded-[var(--r-lg)] border border-hairline bg-surface p-4 shadow-[var(--shadow-sm)] sm:p-5",
        className,
      )}
      {...props}
    >
      {(title || actions) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="truncate text-base font-semibold tracking-tight text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-sm text-ink-muted">{subtitle}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** A translucent liquid-glass card (frosted). Use over imagery or a tinted field. */
export function GlassCard({ strong = false, className, children, ...props }) {
  return (
    <section
      className={cx(strong ? "glass-strong" : "glass", "rounded-[var(--r-lg)] p-4 sm:p-5", className)}
      {...props}
    >
      {children}
    </section>
  );
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  type = "button",
  ...props
}) {
  const variants = {
    primary: "brand-grad text-brand-contrast shadow-[var(--shadow-md)] hover:brightness-[1.06] active:brightness-95",
    secondary: "border border-hairline-strong bg-surface text-ink shadow-[var(--shadow-sm)] hover:bg-surface-3",
    ghost: "text-ink-muted hover:bg-surface-3 hover:text-ink",
    positive: "bg-positive text-white shadow-[var(--shadow-md)] hover:brightness-[1.06] active:brightness-95",
    danger: "border border-danger/40 bg-danger-weak text-danger-ink hover:brightness-[1.03]",
  };
  const sizes = {
    sm: "min-h-9 px-3 text-sm",
    md: "min-h-11 px-4 text-sm",
    lg: "min-h-12 px-5 text-base",
  };
  return (
    <button
      type={type}
      className={cx(
        "focus-ring inline-flex items-center justify-center gap-2 rounded-[var(--r-md)] font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        "[transition-timing-function:var(--ease)] [transition-duration:var(--dur-fast)]",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/** A round icon button (e.g. the swipe affordances). `label` sets the accessible name. */
export function IconButton({ label, tone = "neutral", className, children, type = "button", ...props }) {
  const tones = {
    positive: "bg-positive-weak text-positive-ink hover:brightness-95",
    danger: "bg-danger-weak text-danger-ink hover:brightness-95",
    neutral: "bg-surface-3 text-ink-muted hover:text-ink",
    brand: "bg-brand-weak text-brand hover:brightness-95",
  };
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        "focus-ring inline-flex h-14 w-14 items-center justify-center rounded-full shadow-[var(--shadow-md)] transition active:scale-95",
        tones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function Pill({ tone = "neutral", className, children, ...props }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        TONE[tone] ?? TONE.neutral,
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

/** A status dot + label, for list rows. */
export function StatusPill({ tone = "neutral", children }) {
  const dot = {
    brand: "bg-brand",
    positive: "bg-positive",
    caution: "bg-caution",
    danger: "bg-danger",
    info: "bg-info-ink",
    neutral: "bg-ink-faint",
  };
  return (
    <Pill tone={tone}>
      <span aria-hidden="true" className={cx("h-1.5 w-1.5 rounded-full", dot[tone] ?? dot.neutral)} />
      {children}
    </Pill>
  );
}

export function SectionTitle({ children, hint }) {
  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
      <h1 className="font-display text-[1.7rem] font-semibold leading-[1.1] text-ink">{children}</h1>
      {hint && <div className="text-sm text-ink-muted">{hint}</div>}
    </div>
  );
}

export function Banner({ tone = "info", title, children, className }) {
  const tones = {
    info: "border-[color:var(--info-ink)]/20 bg-info-weak text-info-ink",
    positive: "border-[color:var(--positive)]/25 bg-positive-weak text-positive-ink",
    caution: "border-[color:var(--caution)]/30 bg-caution-weak text-caution-ink",
    danger: "border-[color:var(--danger)]/30 bg-danger-weak text-danger-ink",
  };
  return (
    <div role="status" className={cx("rounded-[var(--r-md)] border p-3 text-sm", tones[tone], className)}>
      {title && <p className="font-semibold">{title}</p>}
      {children && <div className={cx(title && "mt-0.5")}>{children}</div>}
    </div>
  );
}

export function Spinner({ className }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        "inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent opacity-60",
        className,
      )}
    />
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-sm text-ink-muted">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

export function Skeleton({ className }) {
  return <div className={cx("animate-pulse rounded-[var(--r-md)] bg-surface-3", className)} />;
}

export function EmptyState({ icon, title, children, action }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[var(--r-lg)] border border-dashed border-hairline-strong px-6 py-12 text-center">
      {icon && <div className="text-ink-faint">{icon}</div>}
      {title && <p className="font-medium text-ink">{title}</p>}
      {children && <p className="max-w-sm text-sm text-ink-muted">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorText({ error }) {
  if (!error) return null;
  const msg = error instanceof Error ? error.message : String(error);
  return (
    <p role="alert" className="rounded-[var(--r-md)] border border-[color:var(--danger)]/30 bg-danger-weak p-3 text-sm text-danger-ink">
      {msg}
    </p>
  );
}

/** Accessible labelled field: associates the label with its single child control. */
export function Field({ label, hint, children }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const control = isValidElement(children)
    ? cloneElement(children, { id, "aria-describedby": hint ? hintId : undefined })
    : children;
  return (
    <div className="block text-sm">
      <label htmlFor={id} className="mb-1 block font-medium text-ink">
        {label}
      </label>
      {control}
      {hint && (
        <span id={hintId} className="mt-1 block text-xs text-ink-muted">
          {hint}
        </span>
      )}
    </div>
  );
}

export const inputCls =
  "w-full rounded-[var(--r-md)] border border-hairline-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-ink-faint focus-ring focus:border-brand sm:text-sm";
