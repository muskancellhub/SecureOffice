import { useEffect, useMemo, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { DesignInstallAssistance, DesignMilestones, DesignStatus, DesignUpdateVisibility, NetworkDesignDetail, NetworkDesignSummary } from '../types/commerce';

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
  draft: 'Draft',
  reviewed: 'Reviewed',
  submitted: 'Submitted',
  in_review: 'In Review',
  bom_finalized: 'BOM Finalized',
  proposal_ready: 'Proposal Ready',
  approved: 'Approved',
  order_decomposed: 'Order Decomposed',
  fulfillment_in_progress: 'Fulfillment In Progress',
  installation_scheduled: 'Installation Scheduled',
  installed: 'Installed',
  completed: 'Completed',
};

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

const formatStatus = (status: DesignStatus): string => STATUS_LABELS[status] || status;

const defaultMilestones: DesignMilestones = {
  estimatedReviewDate: '',
  estimatedProposalDate: '',
  estimatedFulfillmentDate: '',
  estimatedInstallationDate: '',
  confirmedFulfillmentDate: '',
  confirmedInstallationDate: '',
};

const defaultInstall: DesignInstallAssistance = {
  installMode: 'self_install',
  preferredInstallDate: '',
  installNotes: '',
};

export const AdminDesignSubmissionsPage = () => {
  const { accessToken } = useAuth();
  const [rows, setRows] = useState<NetworkDesignSummary[]>([]);
  const [activeDesignId, setActiveDesignId] = useState<string>('');
  const [activeDesign, setActiveDesign] = useState<NetworkDesignDetail | null>(null);
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
      const data = await commerceApi.listOpsNetworkSubmissions(accessToken);
      setRows(data);
      if (data.length > 0 && !activeDesignId) {
        setActiveDesignId(data[0].id);
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load submitted designs');
    } finally {
      setLoading(false);
    }
  };

  const loadActiveDesign = async (designId: string) => {
    if (!accessToken || !designId) return;
    try {
      const detail = await commerceApi.getNetworkDesign(accessToken, designId);
      setActiveDesign(detail);
      setMilestones({
        estimatedReviewDate: detail.milestones?.estimatedReviewDate || '',
        estimatedProposalDate: detail.milestones?.estimatedProposalDate || '',
        estimatedFulfillmentDate: detail.milestones?.estimatedFulfillmentDate || '',
        estimatedInstallationDate: detail.milestones?.estimatedInstallationDate || '',
        confirmedFulfillmentDate: detail.milestones?.confirmedFulfillmentDate || '',
        confirmedInstallationDate: detail.milestones?.confirmedInstallationDate || '',
      });
      setInstallAssistance({
        installMode: detail.installAssistance?.installMode || 'self_install',
        preferredInstallDate: detail.installAssistance?.preferredInstallDate || '',
        installNotes: detail.installAssistance?.installNotes || '',
      });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load design detail');
    }
  };

  useEffect(() => {
    loadRows();
  }, [accessToken]);

  useEffect(() => {
    if (!activeDesignId) {
      setActiveDesign(null);
      return;
    }
    loadActiveDesign(activeDesignId);
  }, [accessToken, activeDesignId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const onStatusChange = async (designId: string, status: DesignStatus) => {
    if (!accessToken) return;
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignStatus(accessToken, designId, status);
      setRows((prev) => prev.map((row) => (row.id === designId ? updated : row)));
      if (activeDesignId === designId) setActiveDesign(updated);
      setNotice(`Status updated to ${formatStatus(status)}.`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update design status');
    }
  };

  const onAddUpdate = async () => {
    if (!accessToken || !activeDesignId || !noteMessage.trim()) return;
    setError('');
    try {
      const updated = await commerceApi.addNetworkDesignUpdate(accessToken, activeDesignId, {
        visibility: noteVisibility,
        message: noteMessage.trim(),
      });
      setActiveDesign(updated);
      setRows((prev) => prev.map((row) => (row.id === activeDesignId ? updated : row)));
      setNoteMessage('');
      setNotice('Update note posted.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to add update');
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
      setError(err?.response?.data?.detail || 'Failed to update milestones');
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
      setError(err?.response?.data?.detail || 'Failed to update installation preferences');
    }
  };

  const decompositionSections = useMemo(() => {
    if (!activeDesign?.decomposition) return [];
    const entries = Object.entries(activeDesign.decomposition);
    return entries.filter(([, lines]) => Array.isArray(lines) && lines.length > 0);
  }, [activeDesign?.decomposition]);

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <div>
          <h1>Ops Design Queue</h1>
          <p className="lead">Manage the guided fulfillment timeline, customer updates, and demo milestones.</p>
        </div>
      </div>

      {loading && <div className="mini-note">Loading submissions...</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      <article className="dashboard-panel full-width">
        <table className="cart-table">
          <thead>
            <tr>
              <th>Design</th>
              <th>Quote / Order</th>
              <th>Company</th>
              <th>Status</th>
              <th>CapEx</th>
              <th>Latest Update</th>
              <th>Next Milestone</th>
              <th>Progress</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const nextOptions = NEXT_STATUS_OPTIONS[row.status] || [];
              return (
                <tr key={row.id} className={row.id === activeDesignId ? 'selected-row' : ''} onClick={() => setActiveDesignId(row.id)}>
                  <td>{row.designName || row.id.slice(0, 8)}</td>
                  <td>
                    <div className="mini-note">{row.quoteId ? row.quoteId.slice(0, 8).toUpperCase() : '-'}</div>
                    <div className="mini-note">{row.orderId ? row.orderId.slice(0, 8).toUpperCase() : '-'}</div>
                  </td>
                  <td>{row.lead?.companyName || '-'}</td>
                  <td><span className="badge">{formatStatus(row.status)}</span></td>
                  <td>{formatCurrency(row.estimatedCapex)}</td>
                  <td>{row.latestUpdate || '-'}</td>
                  <td>{row.nextMilestone || '-'}</td>
                  <td>
                    {nextOptions.length > 0 ? (
                      <select value={row.status} onChange={(e) => onStatusChange(row.id, e.target.value as DesignStatus)}>
                        <option value={row.status}>{formatStatus(row.status)}</option>
                        {nextOptions.map((next) => (
                          <option key={next} value={next}>{formatStatus(next)}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="mini-note">Completed</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {rows.length === 0 && (
              <tr>
                <td colSpan={8} className="mini-note">No submitted designs in queue.</td>
              </tr>
            )}
          </tbody>
        </table>
      </article>

      {activeDesign && (
        <section className="dashboard-grid">
          <article className="dashboard-panel">
            <h3>Post Update</h3>
            <div className="onboarding-input-grid">
              <label>
                Visibility
                <select value={noteVisibility} onChange={(e) => setNoteVisibility(e.target.value as DesignUpdateVisibility)}>
                  <option value="internal">Internal</option>
                  <option value="customer">Customer</option>
                </select>
              </label>
              <label>
                Message
                <input value={noteMessage} onChange={(e) => setNoteMessage(e.target.value)} placeholder="Waiting on final AP selection" />
              </label>
            </div>
            <button className="secondary-btn" onClick={onAddUpdate} disabled={!noteMessage.trim()}>
              Add Update
            </button>
          </article>

          <article className="dashboard-panel">
            <h3>Milestones</h3>
            <div className="onboarding-input-grid">
              <label>
                Estimated Review
                <input type="date" value={milestones.estimatedReviewDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, estimatedReviewDate: e.target.value }))} />
              </label>
              <label>
                Estimated Proposal
                <input type="date" value={milestones.estimatedProposalDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, estimatedProposalDate: e.target.value }))} />
              </label>
              <label>
                Estimated Fulfillment
                <input type="date" value={milestones.estimatedFulfillmentDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, estimatedFulfillmentDate: e.target.value }))} />
              </label>
              <label>
                Estimated Installation
                <input type="date" value={milestones.estimatedInstallationDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, estimatedInstallationDate: e.target.value }))} />
              </label>
              <label>
                Confirmed Fulfillment
                <input type="date" value={milestones.confirmedFulfillmentDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, confirmedFulfillmentDate: e.target.value }))} />
              </label>
              <label>
                Confirmed Installation
                <input type="date" value={milestones.confirmedInstallationDate || ''} onChange={(e) => setMilestones((prev) => ({ ...prev, confirmedInstallationDate: e.target.value }))} />
              </label>
            </div>
            <button className="secondary-btn" onClick={onSaveMilestones}>Save Milestones</button>
          </article>

          <article className="dashboard-panel">
            <h3>Installation Assistance</h3>
            <div className="onboarding-input-grid">
              <label>
                Install Mode
                <select
                  value={installAssistance.installMode || 'self_install'}
                  onChange={(e) => setInstallAssistance((prev) => ({ ...prev, installMode: e.target.value as DesignInstallAssistance['installMode'] }))}
                >
                  <option value="self_install">Self-install</option>
                  <option value="remote_assistance">Remote/video assistance</option>
                  <option value="onsite_visit">Onsite technician visit</option>
                </select>
              </label>
              <label>
                Preferred Date
                <input
                  type="date"
                  value={installAssistance.preferredInstallDate || ''}
                  onChange={(e) => setInstallAssistance((prev) => ({ ...prev, preferredInstallDate: e.target.value }))}
                />
              </label>
              <label>
                Install Notes
                <input
                  value={installAssistance.installNotes || ''}
                  onChange={(e) => setInstallAssistance((prev) => ({ ...prev, installNotes: e.target.value }))}
                />
              </label>
            </div>
            <button className="secondary-btn" onClick={onSaveInstallAssistance}>Save Install Plan</button>
          </article>

          <article className="dashboard-panel full-width">
            <h3>Order Decomposition (Demo)</h3>
            <div className="integration-grid">
              {decompositionSections.map(([bucket, lines]) => (
                <div key={bucket} className="integration-card">
                  <div className="row-between">
                    <strong>{bucket}</strong>
                    <span className="badge">{(lines || []).length}</span>
                  </div>
                  <ul className="plain-bullets">
                    {(lines || []).slice(0, 4).map((line: any, idx: number) => (
                      <li key={`${bucket}-${idx}`}>{line.name || 'Line item'} x{line.quantity || 0}</li>
                    ))}
                  </ul>
                </div>
              ))}
              {decompositionSections.length === 0 && (
                <div className="integration-card">
                  <p className="mini-note">No decomposition lines yet.</p>
                </div>
              )}
            </div>
          </article>
        </section>
      )}
    </section>
  );
};
