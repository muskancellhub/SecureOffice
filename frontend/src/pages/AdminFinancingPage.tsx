import { useCallback, useEffect, useMemo, useState } from 'react';
import { Building2, CheckCircle2, Landmark, Percent, Plus, Save, Star, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';
import * as productsApi from '../api/productsApi';
import * as commerceApi from '../api/commerceApi';
import { extractApiError } from '../utils/extractApiError';
import type { FinancingTerms } from '../types/products';

const pct = (value: number): string => `${(value * 100).toFixed(2)}%`;

export const AdminFinancingPage = () => {
  const { accessToken, user } = useAuth();
  const { activeTenantId, activeTenant } = useTenant();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';
  const canManage = useMemo(
    () => new Set(user?.effective_permissions ?? []).has('manage_pricing'),
    [user?.effective_permissions],
  );

  const [terms, setTerms] = useState<FinancingTerms[]>([]);
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [creating, setCreating] = useState(false);
  const [savingCommercial, setSavingCommercial] = useState(false);
  const [termModalOpen, setTermModalOpen] = useState(false);

  const [newTerm, setNewTerm] = useState<Record<string, any>>({
    name: '', term_months: 36, annual_rate_pct: 0.05, subscription_interval: 'MONTH', is_default: false,
  });

  // commercial config — targets the active tenant (write-only PUT, no GET)
  const [commercial, setCommercial] = useState<Record<string, any>>({
    default_margin_pct: 0.2, opex_eligible: false, credit_status: 'PENDING', credit_limit: '',
  });

  const load = useCallback(async () => {
    if (!accessToken || !isAdmin) return;
    try {
      const [termRows, profile] = await Promise.all([
        productsApi.listFinancingTerms(accessToken),
        commerceApi.getOnboardingProfile(accessToken).catch(() => null),
      ]);
      setTerms(termRows);
      setOrgName(profile?.organization_name || '');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load financing terms'));
    }
  }, [accessToken, isAdmin, activeTenantId]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(''), 2500);
    return () => window.clearTimeout(t);
  }, [notice]);

  const stats = useMemo(() => {
    const active = terms.filter((t) => t.is_active);
    const def = terms.find((t) => t.is_default);
    const avgRate = terms.length ? terms.reduce((s, t) => s + t.annual_rate_pct, 0) / terms.length : 0;
    return { total: terms.length, active: active.length, def, avgRate };
  }, [terms]);

  const onCreateTerm = async () => {
    if (!accessToken) return;
    setCreating(true);
    setError('');
    try {
      await productsApi.createFinancingTerms(accessToken, {
        name: newTerm.name, term_months: Number(newTerm.term_months),
        annual_rate_pct: Number(newTerm.annual_rate_pct),
        subscription_interval: newTerm.subscription_interval, is_default: newTerm.is_default,
      });
      setNewTerm({ name: '', term_months: 36, annual_rate_pct: 0.05, subscription_interval: 'MONTH', is_default: false });
      setNotice('Financing term created');
      setTermModalOpen(false);
      await load();
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to create financing term'));
    } finally {
      setCreating(false);
    }
  };

  const onSaveCommercial = async () => {
    if (!accessToken || !activeTenantId) return;
    setSavingCommercial(true);
    setError('');
    try {
      await productsApi.updateCustomerCommercial(accessToken, activeTenantId, {
        default_margin_pct: Number(commercial.default_margin_pct),
        opex_eligible: commercial.opex_eligible,
        credit_status: commercial.credit_status,
        credit_limit: commercial.credit_limit === '' ? undefined : Number(commercial.credit_limit),
      });
      setNotice('Customer commercial config saved');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save commercial config'));
    } finally {
      setSavingCommercial(false);
    }
  };

  if (!isAdmin) {
    return <section className="content-wrap fade-in"><div className="error-text">Admin access required.</div></section>;
  }

  return (
    <section className="content-wrap fade-in admin-financing-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><Landmark size={15} /> Admin</span>
          <h1>Financing &amp; commercial</h1>
          <p className="apx-subtitle">Lease terms drive OPEX pricing; per-customer config controls margin &amp; credit.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Building2 size={14} /> Scope: {orgName || activeTenant?.name || 'All tenants'}</span>
            <span className="apx-scope-meta">{stats.total} term{stats.total === 1 ? '' : 's'} · {stats.active} active</span>
          </div>
        </div>
        {canManage && (
          <button className="apx-add-btn" onClick={() => setTermModalOpen(true)}>
            <Plus size={18} /> New term
          </button>
        )}
      </header>

      {error && <div className="error-text">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      <div className="apx-stats">
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Financing terms</span><span className="apx-stat-icon blue"><Landmark size={16} /></span></div>
          <div className="apx-stat-value">{stats.total}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Default term</span><span className="apx-stat-icon violet"><Star size={16} /></span></div>
          <div className="apx-stat-value apx-stat-text">{stats.def?.name || '—'}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Avg. annual rate</span><span className="apx-stat-icon green"><Percent size={16} /></span></div>
          <div className="apx-stat-value">{pct(stats.avgRate)}</div>
        </article>
        <article className="apx-stat">
          <div className="apx-stat-head"><span>Active terms</span><span className="apx-stat-icon amber"><CheckCircle2 size={16} /></span></div>
          <div className="apx-stat-value">{stats.active}</div>
        </article>
      </div>

      {/* Financing terms table */}
      <div className="apx-table-card" style={{ marginBottom: 24 }}>
        <div className="fin-card-title-row">
          <h3 className="apx-modal-title" style={{ margin: 0 }}>Financing terms</h3>
        </div>
        <div className="fin-table">
          <div className="fin-thead">
            <span>Name</span>
            <span className="amx-num">Term</span>
            <span className="amx-num">Annual rate</span>
            <span>Interval</span>
            <span>Default</span>
            <span>Status</span>
          </div>
          {terms.length === 0 && <div className="apx-empty">No financing terms yet.</div>}
          {terms.map((t) => (
            <div key={t.id} className="fin-row">
              <span className="fin-name">{t.name}</span>
              <span className="amx-num">{t.term_months} mo</span>
              <span className="amx-num fin-rate">{pct(t.annual_rate_pct)}</span>
              <span className="fin-interval">{t.subscription_interval === 'YEAR' ? 'Annual' : 'Monthly'}</span>
              <span>{t.is_default ? <span className="fin-default-badge"><Star size={12} /> Default</span> : <span className="fin-muted">—</span>}</span>
              <span>
                <span className={`apx-status apx-status-${t.is_active ? 'active' : 'inactive'}`}>
                  {t.is_active ? 'Active' : 'Inactive'}
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Customer commercial config */}
      {canManage && (
        <div className="apx-table-card fin-config-card">
          <div className="fin-card-title-row">
            <h3 className="apx-modal-title" style={{ margin: 0 }}>Customer commercial config</h3>
          </div>
          <p className="apx-modal-sub" style={{ marginTop: 4 }}>
            Margin, OPEX eligibility &amp; credit for <strong>{activeTenant?.name ?? 'the active tenant'}</strong>. Switch tenants with the top-bar selector.
          </p>

          <div className="fin-config-grid">
            <label className="apx-field">
              <span>Default margin (decimal, e.g. 0.20)</span>
              <input type="number" step="0.0001" value={commercial.default_margin_pct}
                onChange={(e) => setCommercial({ ...commercial, default_margin_pct: e.target.value })} />
            </label>
            <label className="apx-field">
              <span>Credit limit (USD)</span>
              <input type="number" step="0.01" placeholder="—" value={commercial.credit_limit}
                onChange={(e) => setCommercial({ ...commercial, credit_limit: e.target.value })} />
            </label>
            <label className="apx-field">
              <span>Credit status</span>
              <select value={commercial.credit_status} onChange={(e) => setCommercial({ ...commercial, credit_status: e.target.value })}>
                <option value="PENDING">Pending</option>
                <option value="PASS">Pass</option>
                <option value="FAIL">Fail</option>
              </select>
            </label>
            <div className="apx-field">
              <span>OPEX eligible</span>
              <div className="fin-toggle-row">
                <button
                  type="button"
                  className={`amx-toggle ${commercial.opex_eligible ? 'on' : ''}`}
                  role="switch"
                  aria-checked={Boolean(commercial.opex_eligible)}
                  onClick={() => setCommercial({ ...commercial, opex_eligible: !commercial.opex_eligible })}
                />
                <span className="fin-toggle-label">{commercial.opex_eligible ? 'Eligible for OPEX financing' : 'CAPEX only'}</span>
              </div>
            </div>
          </div>

          <div className="fin-config-foot">
            <button className="apx-add-btn" onClick={onSaveCommercial} disabled={savingCommercial || !activeTenantId}>
              <Save size={15} /> {savingCommercial ? 'Saving…' : 'Save config'}
            </button>
          </div>
        </div>
      )}

      {/* New financing term modal */}
      {termModalOpen && (
        <div className="apx-modal-overlay" onClick={() => setTermModalOpen(false)}>
          <div className="apx-modal apx-modal-sm" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setTermModalOpen(false)}><X size={18} /></button>
            <h3 className="apx-modal-title">New financing term</h3>
            <p className="apx-modal-sub">Lease terms feed the OPEX annuity pricing.</p>
            <label className="apx-field">
              <span>Name</span>
              <input placeholder="e.g. Standard 36-mo" value={newTerm.name} onChange={(e) => setNewTerm({ ...newTerm, name: e.target.value })} autoFocus />
            </label>
            <div className="fin-config-grid">
              <label className="apx-field">
                <span>Term (months)</span>
                <input type="number" value={newTerm.term_months} onChange={(e) => setNewTerm({ ...newTerm, term_months: e.target.value })} />
              </label>
              <label className="apx-field">
                <span>Annual rate (decimal)</span>
                <input type="number" step="0.0001" value={newTerm.annual_rate_pct} onChange={(e) => setNewTerm({ ...newTerm, annual_rate_pct: e.target.value })} />
              </label>
              <label className="apx-field">
                <span>Interval</span>
                <select value={newTerm.subscription_interval} onChange={(e) => setNewTerm({ ...newTerm, subscription_interval: e.target.value })}>
                  <option value="MONTH">Monthly</option>
                  <option value="YEAR">Annual</option>
                </select>
              </label>
              <div className="apx-field">
                <span>Default term</span>
                <div className="fin-toggle-row">
                  <button
                    type="button"
                    className={`amx-toggle ${newTerm.is_default ? 'on' : ''}`}
                    role="switch"
                    aria-checked={Boolean(newTerm.is_default)}
                    onClick={() => setNewTerm({ ...newTerm, is_default: !newTerm.is_default })}
                  />
                  <span className="fin-toggle-label">{newTerm.is_default ? 'Set as default' : 'Not default'}</span>
                </div>
              </div>
            </div>
            <div className="apx-modal-foot">
              <button className="apx-ghost-btn" onClick={() => setTermModalOpen(false)}>Cancel</button>
              <button className="apx-add-btn" onClick={onCreateTerm} disabled={creating || !newTerm.name}>
                <Plus size={15} /> {creating ? 'Adding…' : 'Add term'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
