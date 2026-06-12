import { useCallback, useEffect, useMemo, useState } from 'react';
import { Lock, Minus, Plus, X } from 'lucide-react';
import { componentPreview } from '../api/productsApi';
import type { CatalogComponent, CatalogItem } from '../types/commerce';
import type { PreviewResult } from '../types/products';
import { useAuth } from '../context/AuthContext';
import { extractApiError } from '../utils/extractApiError';

/** Phase 7 D9 — the "Bundled" configurator popup.
 *
 * Lists the product's components: required rows are checked + locked,
 * optional rows can be unchecked, PER_LINE / PER_SEAT rows get a qty stepper.
 * Every change re-prices live (per tenant) via /pricing/component-preview and
 * is capacity-guarded against the device's capacity/consumes metadata. */

interface Props {
  product: CatalogItem;
  onClose: () => void;
  onConfirm: (
    selections: Record<string, number>,
    financialModel: 'CAPEX' | 'OPEX',
    interval: 'MONTH' | 'YEAR',
  ) => Promise<void>;
}

const QTY_UOMS = new Set(['PER_LINE', 'PER_SEAT', 'PER_DID', 'PER_HOUR']);

const fmt = (n: number) => `$${n.toFixed(2)}`;

function capacityViolations(
  product: CatalogItem,
  components: CatalogComponent[],
  selections: Record<string, number>,
): string[] {
  const capacity: Record<string, number> = (product.attributes?.capacity as Record<string, number>) || {};
  const used: Record<string, number> = {};
  for (const comp of components) {
    const qty = selections[comp.id] ?? 0;
    if (qty <= 0) continue;
    const consumes: Record<string, number> = (comp.attributes?.consumes as Record<string, number>) || {};
    for (const [resource, perUnit] of Object.entries(consumes)) {
      used[resource] = (used[resource] || 0) + perUnit * qty;
    }
  }
  const violations: string[] = [];
  for (const [resource, total] of Object.entries(used)) {
    const limit = capacity[resource];
    if (limit != null && total > limit) {
      violations.push(`${resource.replace('_', ' ')}: ${total} of ${limit} available`);
    }
  }
  return violations;
}

export default function BundleConfigurator({ product, onClose, onConfirm }: Props) {
  const { accessToken } = useAuth();
  const components = useMemo(
    () => (product.components ?? []).slice().sort((a, b) => Number(b.is_required) - Number(a.is_required)),
    [product.components],
  );

  const [selections, setSelections] = useState<Record<string, number>>(() => {
    const initial: Record<string, number> = {};
    for (const comp of components) {
      if (comp.is_required) initial[comp.id] = Math.max(1, comp.default_qty);
    }
    return initial;
  });
  const [financialModel, setFinancialModel] = useState<'CAPEX' | 'OPEX'>('CAPEX');
  const [interval, setInterval_] = useState<'MONTH' | 'YEAR'>('MONTH');
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const violations = useMemo(
    () => capacityViolations(product, components, selections),
    [product, components, selections],
  );

  useEffect(() => {
    if (!accessToken || !product.product_id) return;
    let cancelled = false;
    componentPreview(accessToken, {
      product_id: product.product_id,
      financial_model: financialModel,
      interval,
      selections,
    })
      .then((result) => {
        if (!cancelled) {
          setPreview(result);
          setError('');
        }
      })
      .catch((err) => {
        if (!cancelled) setError(extractApiError(err, 'Failed to price selection'));
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, product.product_id, financialModel, interval, selections]);

  const priceFor = useCallback((componentId: string): string | null => {
    const line = preview?.lines?.find((l: any) => l.component_id === componentId);
    if (!line) return null;
    return line.billing === 'RECURRING'
      ? `${fmt(Number(line.unit_price))}/${interval === 'YEAR' ? 'yr' : 'mo'}`
      : `${fmt(Number(line.unit_price))} one-time`;
  }, [preview, interval]);

  const toggle = (comp: CatalogComponent) => {
    if (comp.is_required) return;
    setSelections((prev) => {
      const next = { ...prev };
      if (next[comp.id]) delete next[comp.id];
      else next[comp.id] = Math.max(1, comp.default_qty);
      return next;
    });
  };

  const step = (comp: CatalogComponent, delta: number) => {
    setSelections((prev) => {
      const current = prev[comp.id] ?? 0;
      const next = Math.max(comp.is_required ? 1 : 0, current + delta);
      const out = { ...prev };
      if (next <= 0) delete out[comp.id];
      else out[comp.id] = next;
      return out;
    });
  };

  const confirm = async () => {
    if (violations.length) return;
    setBusy(true);
    setError('');
    try {
      await onConfirm(selections, financialModel, interval);
      onClose();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to add to cart'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bcfg-overlay" role="dialog" aria-modal="true" aria-label={`Configure ${product.name}`}>
      <style>{`
        .bcfg-overlay { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.55); display: flex;
          align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
        .bcfg-modal { background: var(--surface, #fff); border-radius: 14px; width: 640px; max-width: 100%;
          max-height: 90vh; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,0.25); }
        .bcfg-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 20px 24px 8px; }
        .bcfg-head h2 { margin: 0; font-size: 1.1rem; }
        .bcfg-sub { color: var(--muted, #64748b); font-size: 0.85rem; margin-top: 4px; }
        .bcfg-toggles { display: flex; gap: 12px; padding: 8px 24px; }
        .bcfg-toggle { display: inline-flex; border: 1px solid var(--border, #e2e8f0); border-radius: 8px; overflow: hidden; }
        .bcfg-toggle button { border: 0; background: transparent; padding: 6px 12px; cursor: pointer; font-size: 0.8rem; }
        .bcfg-toggle button.on { background: var(--accent, #2563eb); color: #fff; }
        .bcfg-rows { overflow-y: auto; padding: 8px 24px; flex: 1; }
        .bcfg-row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border, #eef2f7); }
        .bcfg-row.off { opacity: 0.5; }
        .bcfg-row-name { flex: 1; }
        .bcfg-row-name .label { font-size: 0.9rem; font-weight: 500; }
        .bcfg-row-name .meta { font-size: 0.75rem; color: var(--muted, #64748b); }
        .bcfg-price { font-size: 0.85rem; min-width: 110px; text-align: right; }
        .bcfg-step { display: inline-flex; align-items: center; gap: 6px; }
        .bcfg-step button { width: 24px; height: 24px; border-radius: 6px; border: 1px solid var(--border, #e2e8f0);
          background: transparent; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; }
        .bcfg-foot { padding: 14px 24px 20px; border-top: 1px solid var(--border, #eef2f7); }
        .bcfg-totals { display: flex; gap: 18px; font-size: 0.9rem; margin-bottom: 10px; flex-wrap: wrap; }
        .bcfg-error { color: #dc2626; font-size: 0.8rem; margin-bottom: 8px; }
        .bcfg-actions { display: flex; justify-content: flex-end; gap: 10px; }
        .bcfg-actions .primary { background: var(--accent, #2563eb); color: #fff; border: 0; border-radius: 8px;
          padding: 9px 18px; cursor: pointer; font-weight: 600; }
        .bcfg-actions .primary:disabled { opacity: 0.5; cursor: not-allowed; }
        .bcfg-actions .ghost { background: transparent; border: 1px solid var(--border, #e2e8f0); border-radius: 8px;
          padding: 9px 14px; cursor: pointer; }
        .bcfg-close { background: transparent; border: 0; cursor: pointer; color: var(--muted, #64748b); }
      `}</style>
      <div className="bcfg-modal">
        <div className="bcfg-head">
          <div>
            <h2>Bundled — {product.name}</h2>
            <div className="bcfg-sub">This solution includes:</div>
          </div>
          <button className="bcfg-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        <div className="bcfg-toggles">
          <div className="bcfg-toggle" role="group" aria-label="Financial model">
            <button className={financialModel === 'CAPEX' ? 'on' : ''} onClick={() => setFinancialModel('CAPEX')}>Buy (CAPEX)</button>
            <button className={financialModel === 'OPEX' ? 'on' : ''} onClick={() => setFinancialModel('OPEX')}>Lease (OPEX)</button>
          </div>
          <div className="bcfg-toggle" role="group" aria-label="Billing interval">
            <button className={interval === 'MONTH' ? 'on' : ''} onClick={() => setInterval_('MONTH')}>Monthly</button>
            <button className={interval === 'YEAR' ? 'on' : ''} onClick={() => setInterval_('YEAR')}>Annual</button>
          </div>
        </div>

        <div className="bcfg-rows">
          {components.map((comp) => {
            const selected = (selections[comp.id] ?? 0) > 0 || comp.is_required;
            const qty = selections[comp.id] ?? (comp.is_required ? Math.max(1, comp.default_qty) : 0);
            const showStepper = selected && QTY_UOMS.has(comp.uom);
            return (
              <div key={comp.id} className={`bcfg-row${selected ? '' : ' off'}`}>
                <input
                  type="checkbox"
                  checked={selected}
                  disabled={comp.is_required}
                  onChange={() => toggle(comp)}
                  aria-label={comp.label}
                />
                <div className="bcfg-row-name">
                  <div className="label">
                    {comp.label}{' '}
                    {comp.is_required && <Lock size={12} aria-label="Required" style={{ verticalAlign: 'middle' }} />}
                  </div>
                  <div className="meta">
                    {comp.component_type.replace(/_/g, ' ')} · {comp.uom.replace(/_/g, ' ').toLowerCase()}
                    {!comp.price_editable && ' · PAPI-priced'}
                  </div>
                </div>
                {showStepper && (
                  <div className="bcfg-step">
                    <button onClick={() => step(comp, -1)} aria-label={`Fewer ${comp.label}`}><Minus size={13} /></button>
                    <span>{qty}</span>
                    <button onClick={() => step(comp, 1)} aria-label={`More ${comp.label}`}><Plus size={13} /></button>
                  </div>
                )}
                <div className="bcfg-price">
                  {selected
                    ? priceFor(comp.id)
                      ?? (comp.billing === 'RECURRING' ? `${fmt(comp.monthly_unit)}/mo` : `${fmt(comp.one_time_unit)} one-time`)
                    : '—'}
                </div>
              </div>
            );
          })}
        </div>

        <div className="bcfg-foot">
          {violations.length > 0 && (
            <div className="bcfg-error">
              Capacity exceeded — {violations.join('; ')}.
            </div>
          )}
          {error && <div className="bcfg-error">{error}</div>}
          <div className="bcfg-totals">
            <span><strong>One-time:</strong> {preview ? fmt(Number(preview.one_time_total)) : '…'}</span>
            <span>
              <strong>{interval === 'YEAR' ? 'Annual' : 'Monthly'}:</strong>{' '}
              {preview ? fmt(Number(preview.recurring_total_at_interval ?? preview.monthly_total)) : '…'}
            </span>
            {financialModel === 'OPEX' && preview && (
              <span><strong>Term:</strong> {preview.term_months} mo</span>
            )}
          </div>
          <div className="bcfg-actions">
            <button className="ghost" onClick={onClose}>Cancel</button>
            <button className="primary" onClick={confirm} disabled={busy || violations.length > 0}>
              {busy ? 'Adding…' : 'Add to cart'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
