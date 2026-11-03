"use client";

import { useEffect } from "react";

// Registers the offline-page worker (public/sw.js, D89). It caches only that page: never a page
// of the app, an API response or anything about you.
export function ServiceWorker() {
  useEffect(() => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
  }, []);
  return null;
}
