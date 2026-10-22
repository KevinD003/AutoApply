// Next's /api rewrite proxy prints "Failed to proxy <full URL with query>" when the backend is
// unreachable, and that URL can hold a posting's question key. The event is kept; the URL and
// the error's text are not (only its code, such as ECONNREFUSED).
export function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  const original = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === "string" && args[0].startsWith("Failed to proxy ")) {
      const code = (args[1] as { code?: unknown } | undefined)?.code;
      original(`Failed to proxy an API request to the backend (${typeof code === "string" ? code : "error"})`);
      return;
    }
    original(...args);
  };
}
