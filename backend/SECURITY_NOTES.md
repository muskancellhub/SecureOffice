# Backend security notes

Living record of manual security reviews and accepted-risk exceptions.
Companion to the Bandit/pip-audit gates in `.github/workflows/security.yml`.

## Release-gate evidence (QA_FRAMEWORK §10 — block on high/critical) — 2026-06-11

Post-remediation re-run of the SCA executive report's scans:

| Scan | Result | Gate |
|---|---|---|
| pip-audit (backend env) | 5 findings, 0 high/critical — all accepted exceptions below | **PASS** |
| npm audit frontend (`--audit-level=high`) | 0 high (2 moderate, dev-server only, deferred) | **PASS** |
| npm audit anam_ai | 0 vulnerabilities | **PASS** |
| Bandit SAST (`-r app`) | 0 findings at all severities | **PASS** |

## Manual review: CDW agent subprocess (Bandit B404/B603) — 2026-06-11

`app/services/cdw_agent_service.py` runs a config-driven external command.
Reviewed and accepted, suppressed inline with `# nosec`:

- The command string comes exclusively from the `CDW_AGENT_COMMAND` server
  environment variable (`app/core/config.py`); it is never assembled from
  request data. User-supplied `query`/`limit` are passed via child-process
  env vars (`CDW_QUERY`, `CDW_LIMIT`), not the command line.
- `shlex.split` + `shell=False` — no shell metacharacter interpretation.
- The only route that reaches it, `POST /integrations/cdw/sync-routers`
  (`app/routes/integrations.py`), requires the `PERM_MANAGE_CATALOG_SYNC`
  permission.
- Hardening if the deployment story changes: allowlist the executable path
  rather than trusting the full env-provided command string.

## Accepted SCA exceptions (pip-audit) — 2026-06-11

After upgrading fastapi 0.136.3 / starlette 1.3.0 / authlib 1.6.12 /
python-multipart 0.0.32 and refreshing transitive deps, these remain and are
accepted because no compatible fix exists. Re-check whenever `crewai` is bumped.

| Package | Vuln | Why stuck | Severity |
|---|---|---|---|
| requests 2.32.5 | CVE-2026-25645 (fix 2.33.0) | crewai-tools pins `requests~=2.32.5` | Medium |
| python-dotenv 1.1.1 | CVE-2026-28684 (fix 1.2.2) | crewai pins `~=1.1.1` | Low |
| uv 0.9.30 | GHSA-pjjw-68hj-v9mw, GHSA-4gg8-gxpx-9rph (fix 0.11.x) | crewai pins `uv~=0.9.13`; build tool, not runtime-exposed | Low |
| chromadb 1.1.1 | CVE-2026-45829 (pre-auth RCE on chroma *server*) | no fixed release published; **not applicable here** — see review below | Low (accepted) |

## Manual review: ChromaDB exposure (SCA P1) — 2026-06-11

CVE-2026-45829 is a pre-auth RCE against a network-reachable ChromaDB server.
Verified not applicable to this deployment:

- chromadb is transitive via crewai only; **zero imports** of chromadb in
  `app/`, `scripts/`, or config — no `CHROMA_*` env vars anywhere.
- Every `Crew(...)` in the codebase (`app/services/intake_chat_service.py`,
  `app/services/crew/crew.py`) is constructed without `memory=`, knowledge
  sources, or an embedder — the code paths that would instantiate even an
  *embedded* chroma client never run.
- No chroma server process or listener on the host.

Accepted as Low. Re-verify if crewai memory/RAG features are ever enabled or a
ChromaDB server is deployed — then this becomes a release blocker until a fixed
chromadb ships.

## OAuth retest after authlib 1.6.12 (SCA P0) — 2026-06-11

- Microsoft: `GET /auth/microsoft/login` → 302 to `login.microsoftonline.com`
  with correct `state`/`nonce`/scopes — exercises authlib's metadata fetch,
  session-state storage (starlette 1.3 SessionMiddleware), and redirect build.
  Full code-exchange round-trip requires an interactive Microsoft login —
  perform once before release.
- Google: returns the configured-check 503 (no Google credentials in this
  environment) — unchanged behavior. The no-userinfo fallback bug in
  `routes/auth.py` (`parse_id_token` arg order) was fixed as part of this pass.

Frontend: 2 moderate `esbuild<=0.24.2` advisories remain via vite 5; the fix is
vite 8 (major bump), deferred per `DEPENDENCY_UPGRADE_NOTES.md`. Dev-server
only — not present in production bundles.

## Bandit false positives (inline `# nosec`)

| Rule | Site | Reason |
|---|---|---|
| B608 | `app/routes/anam.py` | f-string is an OpenAI system prompt, not SQL |
| B106 | `app/repositories/refresh_session_repository.py` | empty placeholder hash, set before persist |
| B105 | `app/services/papi_client.py` | OAuth token cache dict, not a credential |
| B405 | `app/services/network_topology_service.py` | builds draw.io XML; never parses external XML |
| B404/B603 | `app/services/cdw_agent_service.py` | see manual review above |
