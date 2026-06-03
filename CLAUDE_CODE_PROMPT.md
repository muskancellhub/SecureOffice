# Claude Code Prompt — Dependency Security + Safe-Patch Upgrade

Copy everything below the line into Claude Code from the repo root (`/Users/muskan/SecureOffice2`).

---

You are upgrading npm dependencies in this monorepo. There are two Node projects:

1. `frontend/` — Vite + React 18 + TypeScript app (`secureoffice2-frontend`)
2. `anam_ai/` — Express 5 server + Vite avatar tool (`anam-avatar`)

## Scope

**In scope:** resolve all open CVEs, apply patch + minor updates within the current major. **Do not** upgrade any major version. Specifically:

- KEEP: React 18, React Router 6, Vite 5 (frontend), Vite 6 (anam_ai), TypeScript 5, lucide-react 0.x, @react-three/fiber 8, @react-three/drei 9, @vitejs/plugin-react 4
- BUMP: anything where the new version stays within the current major

## Target changes

### `frontend/`

| Package | From | To | Why |
|---|---|---|---|
| axios | 1.15.1 | ^1.16.1 | HIGH CVE — GHSA-pjwm-pj3p-43mv (NO_PROXY bypass), GHSA-q8qp-cvcw-x6jj (prototype pollution), GHSA-3w6x-2g7m-8v23, GHSA-3g43-6gmg-66jw, GHSA-35jp-ww65-95wh, GHSA-898c-q2cr-xwhg |
| vite | 5.4.21 | latest 5.4.x patch | moderate CVE in 5.x line (resolves esbuild transitive too) |
| vitest | 4.1.0 | ^4.1.8 | patch |
| framer-motion | 12.34.3 | ^12.40.0 | patch |
| postcss | 8.5.10 | ^8.5.15 | patch |
| autoprefixer | 10.4.24 | ^10.5.0 | minor (no breaking) |
| tailwindcss | 4.2.1 | ^4.3.0 | minor within v4 |
| @types/react | 18.3.28 | ^18.3.30 | patch |
| react-router-dom | 6.30.3 | ^6.30.4 | patch |

Update `package.json` ranges where needed, then `npm install` to refresh `package-lock.json`.

### `anam_ai/`

| Package | From | To | Why |
|---|---|---|---|
| vite | 6.4.1 | latest 6.4.x patch | HIGH CVE on 6.4.1 |
| dotenv | 17.4.0 | ^17.4.2 | patch |

## Steps

For **each** of `frontend/` and `anam_ai/`:

1. `cd` into the project
2. Edit `package.json` to bump the versions listed above
3. Delete `node_modules` and `package-lock.json` only if `npm install` fails to converge; otherwise just `npm install`
4. Run `npm audit` — confirm **0 high, 0 critical**. Moderates that require a major bump are acceptable; flag them in your report but do not fix
5. Run `npm run build`
6. Run `npm test` if a test script exists (frontend has `vitest`)
7. For `frontend/`: confirm the dev server still starts (`npm run dev` — kill after 5 seconds of stable output)

## Verification report

After both projects are done, output a single report to stdout in this exact format:

```
=== UPGRADE REPORT ===
frontend/
  CVEs before:  H=<n> M=<n>
  CVEs after:   H=<n> M=<n>
  Build:        PASS|FAIL
  Tests:        PASS|FAIL|N/A (<count>)
  Packages bumped:
    - <pkg>: <old> -> <new>

anam_ai/
  CVEs before:  H=<n> M=<n>
  CVEs after:   H=<n> M=<n>
  Build:        PASS|FAIL
  Tests:        PASS|FAIL|N/A
  Packages bumped:
    - <pkg>: <old> -> <new>

Residual issues (require major bump, deferred):
  - <pkg> in <project>: <severity> — <advisory URL>

Suggested commit message:
  chore(deps): patch CVEs + safe minor bumps (axios, vite, framer-motion, ...)
```

## Constraints

- Do **not** run `npm audit fix --force` (it will cross major boundaries)
- Do **not** modify any application source code — this is dependency hygiene only
- Do **not** commit; leave the working tree dirty so the human can review the diff
- If any build or test fails after a bump, revert that single package and note it in the residual issues section
- If `npm install` warns about peer dependency conflicts, surface them in the report — do not suppress with `--legacy-peer-deps`

Begin.
