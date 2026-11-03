import { Fraunces, Hanken_Grotesk } from "next/font/google";

import "./globals.css";

import { ServiceWorker } from "@/components/ServiceWorker";

/*
  Typography is the backbone of the NoEfforts identity: an optical serif (Fraunces)
  for display — the wordmark, page titles and hero — paired with a clean, warm
  grotesk (Hanken Grotesk) for everything else. Self-hosted via next/font (no
  external request, no layout shift). This editorial-serif + grotesk pairing is a
  deliberate, crafted signature, not a default system stack.
*/
const fontDisplay = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  style: ["normal"],
  variable: "--font-display",
  display: "swap",
});

const fontBody = Hanken_Grotesk({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-body",
  display: "swap",
});

export const metadata = {
  title: "NoEfforts",
  description: "Job discovery and application preparation you stay in control of.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
  appleWebApp: { capable: true, title: "NoEfforts", statusBarStyle: "default" },
};

export const viewport = { width: "device-width", initialScale: 1, themeColor: "#0c0b12" };

export default function RootLayout({ children }) {
  return (
    <html
      lang="en"
      data-theme="light"
      suppressHydrationWarning
      className={`${fontDisplay.variable} ${fontBody.variable}`}
    >
      <head>
        {/* Apply a stored theme choice before paint (default light). No flash. */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('ne-theme');if(t==='dark'||t==='light'){document.documentElement.setAttribute('data-theme',t);}}catch(e){}})();",
          }}
        />
      </head>
      <body className="antialiased">
        <ServiceWorker />
        {children}
      </body>
    </html>
  );
}
