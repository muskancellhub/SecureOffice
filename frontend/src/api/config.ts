/**
 * Origin resolution for every backend / monitoring URL the browser builds.
 *
 * Both defaults are RELATIVE paths, so a production bundle carries no hostname
 * and the same build runs unchanged on localhost, on the deploy box, and behind
 * a domain later. A reverse proxy is what maps those prefixes onto the real
 * upstreams (nginx in prod; Vite's `server.proxy` in dev).
 *
 * Set VITE_API_BASE_URL / VITE_GRAFANA_URL to an absolute origin only when the
 * upstream genuinely lives on another host with no proxy in front of it. Note
 * that an absolute `http://` origin will be blocked as mixed content once the
 * app itself is served over HTTPS — prefer the proxied relative form.
 */

/** Base for all FastAPI calls. Every module must go through this — a second
 *  hardcoded origin is exactly the bug this module exists to prevent. */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api';

/** Grafana embed origin. Unset means monitoring isn't reachable from this
 *  deployment, and the Grafana tab hides itself (see ZabbixPage) rather than
 *  rendering a wall of iframes pointed at a host the browser can't resolve. */
export const GRAFANA_BASE_URL: string = import.meta.env.VITE_GRAFANA_URL || '';

/** Whether to surface Grafana embeds at all. */
export const GRAFANA_ENABLED: boolean = GRAFANA_BASE_URL !== '';
