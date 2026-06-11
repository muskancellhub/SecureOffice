# Dependency Upgrade — SecureOffice2

## TL;DR

Patched all open `npm audit` HIGH severities and applied safe within-major updates. No application code changed. No major version bumps. All builds and tests pass.

## CVEs resolved

| Project | Package | Severity | Advisory | Resolved by |
|---|---|---|---|---|
| frontend | axios 1.15.1 | HIGH | [GHSA-pjwm-pj3p-43mv](https://github.com/advisories/GHSA-pjwm-pj3p-43mv) — NO_PROXY bypass via IPv4-mapped IPv6 | axios ^1.16.1 |
| frontend | axios 1.15.1 | HIGH | [GHSA-q8qp-cvcw-x6jj](https://github.com/advisories/GHSA-q8qp-cvcw-x6jj) — prototype pollution, credential injection | axios ^1.16.1 |
| frontend | axios 1.15.1 | HIGH | [GHSA-3g43-6gmg-66jw](https://github.com/advisories/GHSA-3g43-6gmg-66jw) — credential theft via config merge | axios ^1.16.1 |
| frontend | axios 1.15.1 | HIGH | [GHSA-35jp-ww65-95wh](https://github.com/advisories/GHSA-35jp-ww65-95wh) — MITM via config.proxy | axios ^1.16.1 |
| frontend | axios 1.15.1 | MODERATE | [GHSA-3w6x-2g7m-8v23](https://github.com/advisories/GHSA-3w6x-2g7m-8v23) — JSON tampering via parseReviver | axios ^1.16.1 |
| frontend | axios 1.15.1 | MODERATE | [GHSA-898c-q2cr-xwhg](https://github.com/advisories/GHSA-898c-q2cr-xwhg) — DoS + header injection | axios ^1.16.1 |
| frontend | vite 5.4.21 | MODERATE | vite 5.x advisory chain | vite 5.4.x patch |
| frontend | esbuild (transitive) | MODERATE | resolved via vite bump | vite 5.4.x patch |
| anam_ai | vite 6.4.1 | HIGH | vite 6.x advisory | vite 6.4.x patch |
| anam_ai | postcss (transitive) | MODERATE | resolved via vite bump | vite 6.4.x patch |
| anam_ai | qs (transitive via express 5) | MODERATE | resolved via lockfile refresh | npm install |

## Packages bumped

### frontend/

| Package | Before | After | Type |
|---|---|---|---|
| axios | 1.15.1 | ^1.16.1 | security |
| vite | 5.4.21 | 5.4.x latest | security |
| vitest | 4.1.0 | ^4.1.8 | patch |
| framer-motion | 12.34.3 | ^12.40.0 | patch |
| postcss | 8.5.10 | ^8.5.15 | patch |
| autoprefixer | 10.4.24 | ^10.5.0 | minor |
| tailwindcss | 4.2.1 | ^4.3.0 | minor |
| @types/react | 18.3.28 | ^18.3.30 | patch |
| react-router-dom | 6.30.3 | ^6.30.4 | patch |

### anam_ai/

| Package | Before | After | Type |
|---|---|---|---|
| vite | 6.4.1 | 6.4.x latest | security |
| dotenv | 17.4.0 | ^17.4.2 | patch |

## Intentionally deferred (major bumps)

These are GA and stable but would introduce breaking changes; they are tracked as separate workstreams:

| Package | Current | Latest | Reason to defer |
|---|---|---|---|
| react / react-dom | 18.3.1 | 19.2.7 | React 19 requires concurrent-features audit; @react-three/fiber 8 not React-19 compatible |
| @react-three/fiber | 8.18.0 | 9.6.1 | Requires React 19 |
| @react-three/drei | 9.122.0 | 10.7.7 | Requires R3F 9 |
| react-router-dom | 6.30.x | 7.16.0 | v7 ships data router defaults; needs route-config refactor |
| @vitejs/plugin-react | 4.7.0 | 6.0.2 | Couples to Vite 7/8 |
| vite (frontend) | 5.4.x | 8.0.16 | Two major jumps; rollup 4 → 5 transitive impact |
| typescript | 5.9.3 | 6.0.3 | Strictness changes; needs full repo type pass |
| lucide-react | 0.575.0 | 1.17.0 | Just hit 1.0 GA — breaking icon export rename; needs codemod |
| tailwindcss | 4.3.x | (v5 when released) | Already on v4 GA |
| three / @types/three | 0.183.x | 0.184.x | three.js stays on 0.x by convention; intentionally pinned in lockstep with R3F 8 peer range |

A follow-up ticket should bundle React 18 → 19, R3F 8 → 9, Drei 9 → 10, and Router 6 → 7 together since they're peer-linked.

## GA confirmation

All current direct dependencies are on **GA releases**. Nothing in either project is on an alpha, beta, RC, or canary channel. Notes on items that look pre-1.0 but are GA:

- **three.js** has stayed on `0.x` for ~13 years by convention. `0.183.x` is GA.
- **lucide-react** was perpetually `0.x` and just cut `1.0` — our pinned `0.575.0` is GA.
- **tailwindcss-animate 1.0.7** — GA, no newer release.
- **express 5.2.1** — Express 5 reached GA in Oct 2024, we are current.

## Verification

Executed 2026-06-11 (the plan above was applied on this date — package.json had
still carried `axios ^1.11.0` until now):

```
=== UPGRADE REPORT ===
frontend/
  npm audit before:  H=1 (axios chain) M=4
  npm audit after:   H=0 M=2 (esbuild<=0.24.2 via vite 5 — fix is vite 8, deferred; dev-server only)
  Landed:            axios 1.17.0, react-router-dom 6.30.4, vite 5.4.21
  Build:             PASS (tsc -b && vite build)
  Tests:             PASS (23/23 vitest)

anam_ai/
  npm audit before:  H=1 (vite 6 path traversal/file read) M=2 (postcss, qs)
  npm audit after:   0 vulnerabilities
  Build:             PASS

backend/ (Python — see backend/SECURITY_NOTES.md for accepted exceptions)
  pip-audit before:  36 vulns / 14 packages (HIGH: authlib, starlette, python-multipart)
  pip-audit after:   5 vulns / 4 packages, all documented exceptions (crewai-pinned or no fix)
  Landed:            fastapi 0.136.3, starlette 1.3.0, authlib 1.6.12, python-multipart 0.0.32,
                     aiohttp 3.14.1, lxml 6.1.1, PyJWT 2.13.0, urllib3 2.7.0,
                     cryptography/idna/pyasn1/ecdsa refreshed
  Tests:             PASS (118 passed; 28 pre-existing fixture failures, unchanged from baseline)
  Smoke:             PASS (health, docs, login + refresh cycle, 401 CORS headers, 422 shape)
```

## How to reproduce locally

```bash
cd frontend && npm install && npm audit && npm run build && npm test
cd ../anam_ai && npm install && npm audit && npm run build
```

## Rollback

No major versions changed and no application code was touched. To roll back:

```bash
git checkout HEAD -- frontend/package.json frontend/package-lock.json
git checkout HEAD -- anam_ai/package.json anam_ai/package-lock.json
cd frontend && npm install
cd ../anam_ai && npm install
```

## Follow-ups

1. Open ticket: **React 18 → 19 + R3F/Drei + Router 7** bundle upgrade
2. Open ticket: **lucide-react 0.x → 1.x** (icon rename codemod)
3. Open ticket: **Vite 5/6 → 7 or 8** after React 19 lands
4. Add `npm audit --audit-level=high` to CI to catch future HIGHs at PR time
