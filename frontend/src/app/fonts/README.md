# Self-hosted fonts

These woff2 files are vendored so the NoEfforts identity type is served by the app
itself — no request to Google Fonts at build or run time. This matters because the
production Docker image is built with **no network** (`npm run build` in
`docker-smoke` / `execution-compose`); `next/font/google` would try to fetch at build
time and fail, so `src/app/layout.jsx` loads these through `next/font/local` instead.

| File | Family | Axis | Source | Licence |
| --- | --- | --- | --- | --- |
| `Fraunces.woff2` | Fraunces (optical serif, display) | variable, weight 300–700, latin | Google Fonts | SIL Open Font License 1.1 |
| `HankenGrotesk.woff2` | Hanken Grotesk (grotesk, body) | variable, weight 300–700, latin | Google Fonts | SIL Open Font License 1.1 |

Both families are published under the SIL Open Font License 1.1, which permits
bundling and redistribution with the application. Only the latin variable subset is
vendored to keep the files small. To refresh, download the latin variable `woff2`
again and replace the file in place (the import in `layout.jsx` is by filename).
