import { cx } from "./cx";

/*
  The NoEfforts mark: a gradient tile with a white "swipe-check" glyph — a single
  stroke that reads both as the forward swipe of the discovery deck and as a check,
  the moment something is handled. The gradient id is instance-unique so several
  marks can render on one page (and inside a standalone preview) without clashing.
*/
let seq = 0;

export function BrandMark({ size = 28, className }) {
  const gid = `ne-mark-${(seq += 1)}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className={cx("shrink-0", className)}
    >
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6c5ce7" />
          <stop offset="0.55" stopColor="#8b7bff" />
          <stop offset="1" stopColor="#5ba8ff" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="11" fill={`url(#${gid})`} />
      <path
        d="M11 21.5 17 27.5 29 12.5"
        stroke="white"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="29" cy="12.5" r="1.9" fill="white" />
    </svg>
  );
}

export function Wordmark({ size = 28, className, showText = true }) {
  return (
    <span className={cx("inline-flex items-center gap-2", className)}>
      <BrandMark size={size} />
      {showText && (
        <span className="text-[1.05rem] font-semibold tracking-tight text-ink">
          No<span className="text-grad">Efforts</span>
        </span>
      )}
    </span>
  );
}
