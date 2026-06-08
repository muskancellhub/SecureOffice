import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import { subscribeToasts, type ToastItem } from '../utils/toast';

const ICON = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const DURATION = 4200;

export const ToastHost = () => {
  const [items, setItems] = useState<(ToastItem & { leaving?: boolean })[]>([]);

  useEffect(() => {
    return subscribeToasts((t) => {
      setItems((prev) => [...prev, t]);
      window.setTimeout(() => {
        setItems((prev) => prev.map((x) => (x.id === t.id ? { ...x, leaving: true } : x)));
      }, DURATION);
      window.setTimeout(() => {
        setItems((prev) => prev.filter((x) => x.id !== t.id));
      }, DURATION + 260);
    });
  }, []);

  const dismiss = (id: number) => {
    setItems((prev) => prev.map((x) => (x.id === id ? { ...x, leaving: true } : x)));
    window.setTimeout(() => setItems((prev) => prev.filter((x) => x.id !== id)), 260);
  };

  if (items.length === 0) return null;

  return createPortal(
    <div className="toast-host" role="region" aria-live="polite">
      {items.map((t) => {
        const Icon = ICON[t.kind];
        return (
          <div key={t.id} className={`toast-item toast-${t.kind} ${t.leaving ? 'leaving' : ''}`} role="status">
            <span className="toast-ico"><Icon size={18} /></span>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-x" aria-label="Dismiss" onClick={() => dismiss(t.id)}><X size={15} /></button>
          </div>
        );
      })}
    </div>,
    document.body,
  );
};
