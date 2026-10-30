import type { Metadata, Viewport } from "next";
import "./globals.css";

import { ServiceWorker } from "@/components/ServiceWorker";

export const metadata: Metadata = {
  title: "NoEfforts",
  description: "Job discovery and application preparation you stay in control of.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
  appleWebApp: { capable: true, title: "NoEfforts", statusBarStyle: "default" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0f172a" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="antialiased">
        <ServiceWorker />
        {children}
      </body>
    </html>
  );
}
