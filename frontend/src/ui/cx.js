// Tiny className joiner — truthy strings only, no dependency.
export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}
