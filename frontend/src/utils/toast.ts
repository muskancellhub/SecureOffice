// App-wide toast bus. Usable from anywhere (components, contexts, api client)
// without prop-drilling — call toast.success / toast.error / toast.info.

export type ToastKind = 'success' | 'error' | 'info';

export interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

let counter = 0;
const listeners = new Set<(t: ToastItem) => void>();
// De-dupe identical messages fired within a short window (avoids double toasts
// when both an action handler and the api interceptor report the same error).
const recent = new Map<string, number>();

function emit(kind: ToastKind, message: string) {
  const msg = (message || '').trim();
  if (!msg) return;
  const key = `${kind}:${msg}`;
  const now = Date.now();
  const last = recent.get(key) || 0;
  if (now - last < 1500) return;
  recent.set(key, now);
  const item: ToastItem = { id: ++counter, kind, message: msg };
  listeners.forEach((l) => l(item));
}

export const toast = {
  success: (message: string) => emit('success', message),
  error: (message: string) => emit('error', message),
  info: (message: string) => emit('info', message),
};

export function subscribeToasts(fn: (t: ToastItem) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
