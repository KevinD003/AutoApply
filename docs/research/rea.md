# REA (Reverse Engineer Anything) — research notes

- Date: 2026-10-19
- Source: https://github.com/morluto/rea (shallow clone at `research/src/rea`), npm `rea-agents` (https://registry.npmjs.org/rea-agents), docs in-repo under `docs/`.
- Labels: **observed** = seen directly in clone / command output; **documented** = REA's own docs/README claim it; **inferred**; **unknown**.

## Identity and pin

| Fact | Label | Source |
|---|---|---|
| Pinned commit: `b4938aed58737293a6987630476632619713f5cd` (committed 2026-10-20T04:01:36+08:00, "feat(artifacts): triage desktop installation directories (#5207)") | observed | `git log -1` in clone |
| `package.json` name `rea-agents`, version `6.7.0`, bins `rea` and `rea-agents` -> `scripts/rea.mjs`, `mcpName` `io.github.morluto/rea` | observed | package.json |
| npm `latest` dist-tag = `6.7.0`, published 2026-10-18T08:12:05Z; no `preinstall`/`install`/`postinstall` scripts in the published manifest (`prepare` exists only in the repo) | observed | registry.npmjs.org/rea-agents |
| License: MIT ("Copyright (c) 2026 morluto"); third-party material keeps its own licenses (THIRD_PARTY_NOTICES.md); commercial tools (IDA, Hopper, JEB) must be separately licensed | observed (LICENSE) / documented (README) | LICENSE, README "License" |
| DISCLAIMER.md: for lawful research/interoperability/software you are authorized to examine; explicitly does not support "bypassing authentication, bot protection or access controls on systems you are not authorized to test" or "copying proprietary software or reproducing its protected code and assets"; user responsible for ToS/licence compliance | observed | DISCLAIMER.md |

## Prerequisites

| Requirement | Label | Source |
|---|---|---|
| Node.js 22.x (>=22.19), 24.x (>=24.11) or 26+; npm. Node 23/25/prereleases unsupported (`engines`: `^22.19.0 \|\| ^24.11.0 \|\| >=26.0.0`) | observed (package.json) / documented | package.json, README, docs/installation.md |
| Linux: procps-compatible `ps` on PATH for Ghidra, JADX, firmware and **static JS/Electron analysis** (refuses before launching child otherwise) | documented | README Quick start; docs/installation.md "Linux owned-process prerequisite" |
| Websites (CDP inspection): a Chrome-family browser **you start yourself** with `--remote-debugging-port=9222 --user-data-dir=/tmp/rea-browser-profile`; REA "does not launch, own, or terminate this browser" | documented | docs/browser-observation.md "Start a browser" |
| Browser scenarios (`capture-browser-scenario`): Playwright (`playwright-core@1.58.2` is a dependency) driving either a launched caller-supplied Chromium executable (`"mode": "launch"`, `executable_path`, `headless` defaults to `true`, provider-owned temporary profile) or an attached CDP endpoint | observed (dependency) / documented | package.json; docs/browser-scenario-contract.md |
| Minimal Linux container note: headed Chromium under Xvfb may never open the DevTools port without GLES/EGL/Mesa DRI libs; `--password-store=basic` avoids keyring stalls | documented | docs/browser-observation.md |
| HAR / Fiddler SAZ: offline, no extra tool (HAR 1.2 only, validated with `har-schema@2.0.0` + ajv); mitmdump only for native mitmproxy captures on Linux | documented | README table; docs/web-network-captures.md |
| Android APKs: headless JADX via `jadx-headless-mcp-0.7.1-all.jar` (SHA-256 `6e5eacf5...ff75` pinned in docs) + **full JDK 17+**, env `REA_JADX_MCP_JAR`; Linux/macOS/Windows x64 | documented | docs/android-analysis.md |
| Native binaries: Hopper, Ghidra or IDA (or caller-supplied objdump/Rizin) | documented | README |
| Container check: Node v22.22.0, `/usr/bin/ps`, `/usr/bin/java` present; no `chromium`/`google-chrome`/`jadx` on PATH | observed | `which`/`node --version` in this container |

## Install / run

| Fact | Label | Source |
|---|---|---|
| Agent setup: `npx rea-agents setup` (interactive, writes MCP registration + skill files with backups; restart agent). Supported `--client` values include `claude_code`, `codex`, `cursor`, `gemini_cli`, etc. | documented | README; docs/installation.md "Supported agents" |
| Manual MCP registration: `{"command":"npx","args":["-y","rea-agents@6.7.0","mcp"]}` | documented | docs/installation.md "MCP Registry" |
| One-off CLI: `npx -y rea-agents@latest analyze-javascript-application /abs/path --json`; global: `npm install --global rea-agents` then `rea --help` | documented | README |
| Readiness: `rea doctor` (read-only), scoped e.g. `rea doctor --provider ghidra --json` | documented | docs/installation.md |
| **Verified**: `npm exec --yes --ignore-scripts --cache <scratch> --package=rea-agents@6.7.0 -- rea-agents --help` (HOME pointed at a scratch dir, no credentials) printed `rea@6.7.0 — Reverse engineer anything from your terminal or agent.` and the command list. Only warning: `prebuild-install@7.1.3` deprecated. | observed | run on 2026-10-19 in `research/npx-rea/` |

Exact verified setup instruction (no agent registration, no global install):

```bash
mkdir -p ./npx-rea/cache ./npx-rea/home && cd ./npx-rea
HOME=$PWD/home npm exec --yes --ignore-scripts --cache $PWD/cache \
  --package=rea-agents@6.7.0 -- rea-agents --help
```

(`--ignore-scripts` was my precaution; untested whether native deps such as `@lydell/node-pty` then work for PTY-based commands — **unknown**.)

## Tools / modes relevant to NoEfforts (observed in `--help` output unless stated)

- Static JS/Electron: `analyze-javascript-application`, `compare-javascript-export-shapes`, `compare-application-versions`, `compare-source-to-bundle`.
- Web/browser (CDP, passive): `list-browser-targets`, `inspect-web-page`, `analyze-web-bundle` (parses scripts without execution; route/endpoint candidates, source maps), `observe-web-session`, `discover-webmcp-tools`, `capture-web-screenshot`, `compare-web-captures`, `compare-web-screenshots`, `export-web-scripts`.
- Browser scenario (active, Playwright): `capture-browser-scenario` — declarative action list, headless by default (documented).
- HAR/SAZ: `inspect-web-network-capture <file> har --json` (documented in docs/web-network-captures.md; offline).
- Android: `inspect-android-package`, `inspect-android-class`, `inspect-android-method`, `decode-android-resources` (apktool), `identify-flutter-build`, ADB commands.
- Electron: `inspect-electron-fuses`, `inspect-electron-page`, `capture-electron-scenario`.
- Plus native (decompile/function/inspect-macho…), Go/Rust/WASM/EVM/SQLite/pcap/firmware — not relevant here.
- Documented: CDP surfaces are "a passive reverse-engineering capability, not a general browser automation or remote-control surface"; REA never exposes `WebMCP.invokeTool`.

## Host compatibility

- **documented**: macOS, Linux, Windows (Windows Ghidra experimental); many lanes Linux-x64-specific (pwntools, EVM, TShark); APK lane x64 only.
- **documented**: setup supports ~24 agent clients incl. Claude Code.

## API keys / LLM credentials

- **observed**: no references to `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` in `src/`; `--help` ran with no credentials.
- **documented**: "Analysis runs locally"; REA is called *by* an agent over MCP; the agent's model provider sees results. REA itself needs no LLM key (**inferred** from the above). Commercial decompilers need their own licences.

## Usable in a headless Linux container without a logged-in browser?

- **Yes for static/offline lanes** (inferred from docs + observed `--help`): static JS bundle analysis of downloaded/exported scripts, HAR inspection, APK inspection (after JDK17 + jadx-headless-mcp jar), .NET, etc.
- **Browser lanes need a Chromium binary** (not present in this container — observed). `capture-browser-scenario` can launch it headless with a temporary profile (documented), so no logged-in browser is required for public pages. CDP inspection needs you to start Chromium with `--remote-debugging-port`; headless Chromium should work but REA docs only discuss headed-under-Xvfb issues — headless CDP behaviour is **unknown/untested here**.
- Inspecting logged-in competitor surfaces (e.g. a Tsenta dashboard) would require a signed-in profile — out of scope and potentially a ToS issue (see tsenta.md).

## Actual involvement in this project (as of 2026-10-19)

| Question | Answer |
|---|---|
| Installed? | Fetched once into a throwaway npm cache with `--ignore-scripts`; not installed in the repository or globally. |
| Started? | Yes, once: `rea-agents --help` (prints version and command list). |
| Used for an investigation? | **No.** No REA analysis command (`analyze-javascript-application`, HAR analysis, `capture-browser-scenario`, APK tools) has been run against any target. |
| Evidence produced? | None beyond the `--help` output. No Tsenta extension, dashboard, HAR or APK has been analysed. |
| Effect on NoEfforts | None. All NoEfforts code is independent and does not depend on REA. |

Correction: the first pass said no Chromium was available. A Playwright Chromium build *is*
present at `/opt/pw-browsers/chromium-*/chrome-linux/chrome` (used by our own end-to-end tests);
it is just not on `PATH`. REA browser scenarios could be pointed at it with `executable_path`.

Any future REA use must be on public material or our own captures (for example a HAR of
NoEfforts itself), consistent with decision D8 and Tsenta's terms.
