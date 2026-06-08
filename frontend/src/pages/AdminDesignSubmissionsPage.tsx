import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArrowRight, Globe, Save, Settings2, ShieldCheck, X } from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import * as tenantSettingsApi from '../api/tenantSettingsApi';
import { useAuth } from '../context/AuthContext';
import { useTenant } from '../context/TenantContext';
import type { DesignInstallAssistance, DesignMilestones, DesignStatus, DesignUpdateVisibility, NetworkDesignDetail, NetworkDesignSummary } from '../types/commerce';
import type { TenantSettings } from '../types/tenantSettings';
import { extractApiError } from '../utils/extractApiError';
import { toast } from '../utils/toast';

const NEXT_STATUS_OPTIONS: Record<DesignStatus, DesignStatus[]> = {
  draft: ['reviewed', 'submitted'],
  reviewed: ['submitted'],
  submitted: ['in_review'],
  in_review: ['bom_finalized'],
  bom_finalized: ['proposal_ready'],
  proposal_ready: ['approved'],
  approved: ['order_decomposed'],
  order_decomposed: ['fulfillment_in_progress'],
  fulfillment_in_progress: ['installation_scheduled', 'installed'],
  installation_scheduled: ['installed'],
  installed: ['completed'],
  completed: [],
};

const STATUS_LABELS: Record<DesignStatus, string> = {
  draft: 'Draft', reviewed: 'Reviewed', submitted: 'Submitted', in_review: 'In Review',
  bom_finalized: 'BOM Finalized', proposal_ready: 'Proposal Ready', approved: 'Approved',
  order_decomposed: 'Order Decomposed', fulfillment_in_progress: 'Fulfillment In Progress',
  installation_scheduled: 'Installation Scheduled', installed: 'Installed', completed: 'Completed',
};

// Friendly action label for advancing INTO a given status.
const ADVANCE_LABEL: Record<DesignStatus, string> = {
  draft: 'Move to draft', reviewed: 'Mark reviewed', submitted: 'Submit', in_review: 'Start review',
  bom_finalized: 'Finalize BOM', proposal_ready: 'Mark proposal ready', approved: 'Approve',
  order_decomposed: 'Decompose order', fulfillment_in_progress: 'Start fulfillment',
  installation_scheduled: 'Schedule installation', installed: 'Mark installed', completed: 'Complete',
};

// Pipeline columns shown on the board (the design-ops working stages).
const PIPELINE: { key: DesignStatus; label: string }[] = [
  { key: 'submitted', label: 'Submitted' },
  { key: 'in_review', label: 'In Review' },
  { key: 'bom_finalized', label: 'BOM Finalized' },
  { key: 'proposal_ready', label: 'Proposal Ready' },
  { key: 'approved', label: 'Approved' },
];

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);

const formatDate = (s?: string | null): string => (s ? String(s).slice(0, 10) : '');
const formatStatus = (status: DesignStatus): string => STATUS_LABELS[status] || status;

const initialsOf = (name: string): string => {
  const parts = (name || '?').trim().split(/[\s._-]+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? '').join('') || '?';
};
const AVATAR_TONES = ['indigo', 'blue', 'violet', 'teal', 'rose'];
const avatarTone = (seed: string): string => {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AVATAR_TONES[h % AVATAR_TONES.length];
};

const defaultMilestones: DesignMilestones = {
  estimatedReviewDate: '', estimatedProposalDate: '', estimatedFulfillmentDate: '',
  estimatedInstallationDate: '', confirmedFulfillmentDate: '', confirmedInstallationDate: '',
};
const defaultInstall: DesignInstallAssistance = { installMode: 'self_install', preferredInstallDate: '', installNotes: '' };

export const AdminDesignSubmissionsPage = () => {
  const { accessToken } = useAuth();
  const { activeTenant, activeTenantId } = useTenant();
  const [settings, setSettings] = useState<TenantSettings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [rows, setRows] = useState<NetworkDesignSummary[]>([]);
  const [activeDesignId, setActiveDesignId] = useState<string>('');
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverCol, setDragOverCol] = useState<string | null>(null);
  const [activeDesign, setActiveDesign] = useState<NetworkDesignDetail | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [noteMessage, setNoteMessage] = useState('');
  const [noteVisibility, setNoteVisibility] = useState<DesignUpdateVisibility>('internal');
  const [milestones, setMilestones] = useState<DesignMilestones>(defaultMilestones);
  const [installAssistance, setInstallAssistance] = useState<DesignInstallAssistance>(defaultInstall);

  const loadRows = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      setRows(await commerceApi.listOpsNetworkSubmissions(accessToken));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load submitted designs'));
    } finally {
      setLoading(false);
    }
  };

  const loadActiveDesign = async (designId: string) => {
    if (!accessToken || !designId) return;
    try {
      const detail = await commerceApi.getNetworkDesign(accessToken, designId);
      setActiveDesign(detail);
      setMilestones({ ...defaultMilestones, ...(detail.milestones || {}) });
      setInstallAssistance({ ...defaultInstall, ...(detail.installAssistance || {}) });
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load design detail'));
    }
  };

  useEffect(() => { loadRows(); }, [accessToken]);

  const loadSettings = useCallback(async () => {
    if (!accessToken) return;
    try {
      setSettings(await tenantSettingsApi.getTenantSettings(accessToken));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load design-ops settings'));
    }
  }, [accessToken, activeTenantId]);

  useEffect(() => { loadSettings(); }, [loadSettings]);

  const designOps = settings?.design_ops ?? { sla_default_days: 5, auto_assign: false };
  const setDesignOps = (patch: Partial<TenantSettings['design_ops']>) => {
    setSettings((prev) => {
      const base: TenantSettings = prev ?? {
        tenant_id: activeTenantId ?? '', design_ops: { sla_default_days: 5, auto_assign: false },
        admin_services: { enabled_categories: {} }, feature_flags: {}, updated_at: null,
      };
      return { ...base, design_ops: { ...base.design_ops, ...patch } };
    });
  };
  const saveDesignOps = async () => {
    if (!accessToken || !settings) return;
    setSavingSettings(true);
    setError('');
    try {
      const updated = await tenantSettingsApi.updateTenantSettings(accessToken, { design_ops: settings.design_ops });
      setSettings(updated);
      setNotice('Design-ops settings saved.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to save design-ops settings'));
    } finally {
      setSavingSettings(false);
    }
  };

  useEffect(() => {
    if (!activeDesignId) { setActiveDesign(null); return; }
    loadActiveDesign(activeDesignId);
  }, [accessToken, activeDesignId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const onAdvance = async (designId: string, status: DesignStatus) => {
    if (!accessToken) return;
    setAdvancing(true);
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignStatus(accessToken, designId, status);
      setRows((prev) => prev.map((row) => (row.id === designId ? updated : row)));
      if (activeDesignId === designId) setActiveDesign(updated);
      setNotice(`Moved to ${formatStatus(status)}.`);
      toast.success(`Moved to ${formatStatus(status)}`);
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update design status'));
    } finally {
      setAdvancing(false);
    }
  };

  // Drop a dragged design card into a pipeline column → set that status.
  const onDropToColumn = (status: DesignStatus) => {
    const id = draggingId;
    setDraggingId(null);
    setDragOverCol(null);
    if (!id) return;
    const row = rows.find((r) => r.id === id);
    if (!row || row.status === status) return;
    void onAdvance(id, status);
  };

  const onAddUpdate = async () => {
    if (!accessToken || !activeDesignId || !noteMessage.trim()) return;
    setError('');
    try {
      const updated = await commerceApi.addNetworkDesignUpdate(accessToken, activeDesignId, {
        visibility: noteVisibility, message: noteMessage.trim(),
      });
      setActiveDesign(updated);
      setRows((prev) => prev.map((row) => (row.id === activeDesignId ? updated : row)));
      setNoteMessage('');
      setNotice('Update note posted.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to add update'));
    }
  };

  const onSaveMilestones = async () => {
    if (!accessToken || !activeDesignId) return;
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignMilestones(accessToken, activeDesignId, milestones);
      setActiveDesign(updated);
      setRows((prev) => prev.map((row) => (row.id === activeDesignId ? updated : row)));
      setNotice('Milestones updated.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update milestones'));
    }
  };

  const onSaveInstallAssistance = async () => {
    if (!accessToken || !activeDesignId) return;
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignInstallAssistance(accessToken, activeDesignId, installAssistance);
      setActiveDesign(updated);
      setRows((prev) => prev.map((row) => (row.id === activeDesignId ? updated : row)));
      setNotice('Installation preferences updated.');
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to update installation preferences'));
    }
  };

  const board = useMemo(() => {
    const covered = new Set(PIPELINE.map((c) => c.key));
    const columns = PIPELINE.map((col) => ({ ...col, cards: rows.filter((r) => r.status === col.key) }));
    const leftover = rows.filter((r) => !covered.has(r.status));
    return { columns, leftover };
  }, [rows]);

  const decompositionSections = useMemo(() => {
    if (!activeDesign?.decomposition) return [];
    return Object.entries(activeDesign.decomposition).filter(([, lines]) => Array.isArray(lines) && lines.length > 0);
  }, [activeDesign?.decomposition]);

  const renderCard = (row: NetworkDesignSummary) => {
    const contact = row.lead?.fullName || row.lead?.companyName || '—';
    return (
      <button
        key={row.id}
        type="button"
        className={`dq-card ${draggingId === row.id ? 'dragging' : ''}`}
        draggable
        onDragStart={(e) => { setDraggingId(row.id); e.dataTransfer.effectAllowed = 'move'; }}
        onDragEnd={() => { setDraggingId(null); setDragOverCol(null); }}
        onClick={() => setActiveDesignId(row.id)}
      >
        <h4 className="dq-card-title">{row.designName || `Design ${row.id.slice(0, 8)}`}</h4>
        <span className="dq-card-company">{row.lead?.companyName || 'No company'}</span>
        <div className="dq-card-mid">
          <span className="dq-card-capex">{formatCurrency(row.estimatedCapex)}</span>
          <span className="dq-card-date">{formatDate(row.submittedAt || row.createdAt)}</span>
        </div>
        <div className="dq-card-foot">
          <span className={`dq-avatar tone-${avatarTone(contact)}`}>{initialsOf(contact)}</span>
          <span className="dq-card-contact">{contact}</span>
        </div>
      </button>
    );
  };

  return (
    <section className="content-wrap fade-in design-queue-page">
      <header className="apx-header">
        <div className="apx-header-text">
          <span className="apx-eyebrow"><ShieldCheck size={15} /> Admin</span>
          <h1>Design ops queue</h1>
          <p className="apx-subtitle">Review submitted designs and move them through the fulfillment pipeline.</p>
          <div className="apx-scope">
            <span className="apx-scope-chip"><Globe size={14} /> Scope: {activeTenant?.name || 'All tenants'}</span>
            <span className="apx-scope-meta">{rows.length} in queue</span>
          </div>
        </div>
        <button className="apx-ghost-btn dq-settings-btn" onClick={() => setShowSettings((v) => !v)}>
          <Settings2 size={16} /> Queue settings
        </button>
      </header>

      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      {showSettings && (
        <div className="apx-table-card dq-settings-card">
          <h3 className="apx-modal-title" style={{ margin: '0 0 4px' }}>Queue settings</h3>
          <p className="apx-modal-sub" style={{ marginTop: 0 }}>
            Defaults for <strong>{activeTenant?.name ?? 'the active tenant'}</strong> — switch tenants with the top-bar selector.
          </p>
          <div className="dq-settings-fields">
            <label className="apx-field">
              <span>Default SLA (days)</span>
              <input type="number" min={0} max={365} value={designOps.sla_default_days}
                onChange={(e) => setDesignOps({ sla_default_days: Number(e.target.value) })} />
            </label>
            <label className="dq-checkbox">
              <input type="checkbox" checked={designOps.auto_assign} onChange={(e) => setDesignOps({ auto_assign: e.target.checked })} />
              Auto-assign new submissions
            </label>
          </div>
          <button className="apx-add-btn" onClick={saveDesignOps} disabled={savingSettings || !settings}>
            <Save size={15} /> {savingSettings ? 'Saving…' : 'Save settings'}
          </button>
        </div>
      )}

      {loading && <div className="mini-note">Loading submissions…</div>}

      <div className="dq-board">
        {board.columns.map((col) => (
          <div
            key={col.key}
            className={`dq-col ${dragOverCol === col.key ? 'drag-over' : ''}`}
            onDragOver={(e) => { if (draggingId) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setDragOverCol(col.key); } }}
            onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOverCol((c) => (c === col.key ? null : c)); }}
            onDrop={(e) => { e.preventDefault(); onDropToColumn(col.key); }}
          >
            <div className="dq-col-head">
              <span className={`dq-pill dq-pill-${col.key}`}>{col.label}</span>
              <span className="dq-col-count">{col.cards.length}</span>
            </div>
            <div className="dq-col-body">
              {col.cards.map(renderCard)}
              {col.cards.length === 0 && <div className="dq-col-empty">Drop here</div>}
            </div>
          </div>
        ))}
        {board.leftover.length > 0 && (
          <div className="dq-col">
            <div className="dq-col-head">
              <span className="dq-pill dq-pill-other">Later stages</span>
              <span className="dq-col-count">{board.leftover.length}</span>
            </div>
            <div className="dq-col-body">{board.leftover.map(renderCard)}</div>
          </div>
        )}
      </div>

      {!loading && rows.length === 0 && <p className="mini-note">No submitted designs in the queue.</p>}

      {/* Design detail + pipeline actions */}
      {activeDesign && (
        <div className="apx-modal-overlay" onClick={() => setActiveDesignId('')}>
          <div className="apx-modal apx-modal-lg dq-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <button className="apx-modal-close" aria-label="Close" onClick={() => setActiveDesignId('')}><X size={18} /></button>

            <div className="dq-modal-head">
              <div>
                <h3 className="apx-modal-title" style={{ margin: 0 }}>{activeDesign.designName || `Design ${activeDesign.id.slice(0, 8)}`}</h3>
                <p className="apx-modal-sub" style={{ margin: '4px 0 0' }}>
                  {activeDesign.lead?.companyName || 'No company'} · {formatCurrency(activeDesign.estimatedCapex)}
                </p>
              </div>
              <span className={`dq-pill dq-pill-${activeDesign.status}`}>{formatStatus(activeDesign.status)}</span>
            </div>

            {/* Pipeline advance actions */}
            <div className="dq-actions">
              {(NEXT_STATUS_OPTIONS[activeDesign.status] || []).length === 0 ? (
                <span className="mini-note">No further pipeline steps.</span>
              ) : (
                (NEXT_STATUS_OPTIONS[activeDesign.status] || []).map((next, idx) => (
                  <button
                    key={next}
                    className={idx === 0 ? 'apx-add-btn' : 'apx-ghost-btn'}
                    onClick={() => onAdvance(activeDesign.id, next)}
                    disabled={advancing}
                  >
                    {ADVANCE_LABEL[next]} <ArrowRight size={15} />
                  </button>
                ))
              )}
            </div>

            <div className="dq-modal-grid">
              <section className="dq-section">
                <h4>Post update</h4>
                <label className="apx-field">
                  <span>Visibility</span>
                  <select value={noteVisibility} onChange={(e) => setNoteVisibility(e.target.value as DesignUpdateVisibility)}>
                    <option value="internal">Internal</option>
                    <option value="customer">Customer</option>
                  </select>
                </label>
                <label className="apx-field">
                  <span>Message</span>
                  <input value={noteMessage} onChange={(e) => setNoteMessage(e.target.value)} placeholder="Waiting on final AP selection" />
                </label>
                <button className="apx-ghost-btn" onClick={onAddUpdate} disabled={!noteMessage.trim()}>Add update</button>
              </section>

              <section className="dq-section">
                <h4>Installation assistance</h4>
                <label className="apx-field">
                  <span>Install mode</span>
                  <select value={installAssistance.installMode || 'self_install'}
                    onChange={(e) => setInstallAssistance((p) => ({ ...p, installMode: e.target.value as DesignInstallAssistance['installMode'] }))}>
                    <option value="self_install">Self-install</option>
                    <option value="remote_assistance">Remote/video assistance</option>
                    <option value="onsite_visit">Onsite technician visit</option>
                  </select>
                </label>
                <label className="apx-field">
                  <span>Preferred date</span>
                  <input type="date" value={installAssistance.preferredInstallDate || ''}
                    onChange={(e) => setInstallAssistance((p) => ({ ...p, preferredInstallDate: e.target.value }))} />
                </label>
                <button className="apx-ghost-btn" onClick={onSaveInstallAssistance}>Save install plan</button>
              </section>

              <section className="dq-section dq-section-wide">
                <h4>Milestones</h4>
                <div className="dq-milestones">
                  <label className="apx-field"><span>Estimated review</span>
                    <input type="date" value={milestones.estimatedReviewDate || ''} onChange={(e) => setMilestones((p) => ({ ...p, estimatedReviewDate: e.target.value }))} /></label>
                  <label className="apx-field"><span>Estimated proposal</span>
                    <input type="date" value={milestones.estimatedProposalDate || ''} onChange={(e) => setMilestones((p) => ({ ...p, estimatedProposalDate: e.target.value }))} /></label>
                  <label className="apx-field"><span>Estimated fulfillment</span>
                    <input type="date" value={milestones.estimatedFulfillmentDate || ''} onChange={(e) => setMilestones((p) => ({ ...p, estimatedFulfillmentDate: e.target.value }))} /></label>
                  <label className="apx-field"><span>Estimated installation</span>
                    <input type="date" value={milestones.estimatedInstallationDate || ''} onChange={(e) => setMilestones((p) => ({ ...p, estimatedInstallationDate: e.target.value }))} /></label>
                </div>
                <button className="apx-ghost-btn" onClick={onSaveMilestones}>Save milestones</button>
              </section>

              {decompositionSections.length > 0 && (
                <section className="dq-section dq-section-wide">
                  <h4>Order decomposition</h4>
                  <div className="dq-decomp">
                    {decompositionSections.map(([bucket, lines]) => (
                      <div key={bucket} className="dq-decomp-card">
                        <div className="dq-decomp-head"><strong>{bucket}</strong><span className="dq-col-count">{(lines || []).length}</span></div>
                        <ul>
                          {(lines || []).slice(0, 5).map((line: any, idx: number) => (
                            <li key={`${bucket}-${idx}`}>{line.name || 'Line item'} ×{line.quantity || 0}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
