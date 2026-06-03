function formatFieldName(loc: any[]): string {
  const field = loc.filter((p) => p !== 'body' && typeof p === 'string').pop();
  if (!field) return '';
  return field
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c: string) => c.toUpperCase());
}

function formatEntry(e: any): string {
  const msg: string = e?.msg || '';
  if (!msg) return '';
  const loc: any[] = e?.loc;
  if (!Array.isArray(loc) || loc.length === 0) return msg;
  const name = formatFieldName(loc);
  if (!name) return msg;
  const clean = msg
    .replace(/^Value error, /i, '')
    .replace(/^String s/, 's');
  return `${name}: ${clean}`;
}

const EMAIL_RE = /^[a-zA-Z][a-zA-Z0-9._%+\-]*@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$/;

export function isValidEmail(email: string): boolean {
  return EMAIL_RE.test(email);
}

export function extractApiError(err: any, fallback: string): string {
  const detail = err?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.map(formatEntry).filter(Boolean);
    return msgs.length ? msgs.join('. ') : fallback;
  }
  return fallback;
}
