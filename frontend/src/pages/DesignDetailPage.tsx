import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { DrawioDiagramViewer } from '../components/DrawioDiagramViewer';
import { useAuth } from '../context/AuthContext';
import type {
  DesignInstallAssistance,
  DesignStatus,
  DesignStatusHistoryEntry,
  DesignUpdate,
  ManagedServicesDesignSummary,
  ManagedServiceDeviceEntry,
  NetworkBomLine,
  NetworkDesignDetail,
} from '../types/commerce';

type LeadState = {
  fullName: string;
  email: string;
  companyName: string;
  phone: string;
  notes: string;
};

const STATUS_FLOW: DesignStatus[] = [
  'submitted',
  'in_review',
  'bom_finalized',
  'proposal_ready',
  'approved',
  'order_decomposed',
  'fulfillment_in_progress',
  'installation_scheduled',
  'installed',
  'completed',
];

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

const isQuoteRequiredLine = (line: NetworkBomLine): boolean => {
  const unit = Number(line.unit_price || 0);
  if (unit > 0) return false;
  const source = String(line.source_type || '').toLowerCase();
  return source === 'paapi' || source === 'derived';
};

const formatBomMoney = (line: NetworkBomLine, kind: 'unit' | 'total'): string => {
  const value = kind === 'unit' ? Number(line.unit_price || 0) : Number(line.line_total || 0);
  if (value <= 0 && isQuoteRequiredLine(line)) return 'Price on request';
  return formatCurrency(value);
};

const connectivityLabel = (value: NetworkBomLine['connectivity'] | undefined): string | null => {
  if (value === 'wired') return 'Wired link';
  if (value === 'wireless') return 'Wireless link';
  if (value === 'sim') return 'SIM / 5G link';
  return null;
};

const formatDate = (value?: string | null): string => {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
};

const formatStatus = (status: DesignStatus): string => STATUS_LABELS[status] || status;

const defaultInstallState: DesignInstallAssistance = {
  installMode: 'self_install',
  preferredInstallDate: '',
  installNotes: '',
};

export const DesignDetailPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { designId } = useParams();
  const [design, setDesign] = useState<NetworkDesignDetail | null>(null);
  const [lead, setLead] = useState<LeadState>({ fullName: '', email: '', companyName: '', phone: '', notes: '' });
  const [installAssistance, setInstallAssistance] = useState<DesignInstallAssistance>(defaultInstallState);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savingInstall, setSavingInstall] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [msData, setMsData] = useState<ManagedServicesDesignSummary | null>(null);
  const [msSaving, setMsSaving] = useState(false);

  const loadDesign = async () => {
    if (!accessToken || !designId) return;
    setLoading(true);
    setError('');
    try {
      const data = await commerceApi.getNetworkDesign(accessToken, designId);
      setDesign(data);
      // Always fetch managed services via dedicated endpoint for freshest data
      loadManagedServices(data.id);
      setLead({
        fullName: data.lead?.fullName || '',
        email: data.lead?.email || '',
        companyName: data.lead?.companyName || '',
        phone: data.lead?.phone || '',
        notes: data.lead?.notes || '',
      });
      setInstallAssistance({
        installMode: data.installAssistance?.installMode || 'self_install',
        preferredInstallDate: data.installAssistance?.preferredInstallDate || '',
        installNotes: data.installAssistance?.installNotes || '',
      });
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load design details');
    } finally {
      setLoading(false);
    }
  };

  const loadManagedServices = useCallback(async (id?: string) => {
    const did = id || designId;
    if (!accessToken || !did) return;
    try {
      const data = await commerceApi.getDesignManagedServices(accessToken, did);
      setMsData(data);
    } catch (err) {
      console.warn('[ManagedServices] Failed to load:', err);
    }
  }, [accessToken, designId]);

  useEffect(() => {
    loadDesign();
  }, [accessToken, designId]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(''), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const bomLines = useMemo(() => {
    const lines = (design?.bom as { line_items?: NetworkBomLine[] })?.line_items;
    return Array.isArray(lines) ? lines : [];
  }, [design?.bom]);

  const quoteRequiredCount = useMemo(
    () => bomLines.filter((line) => isQuoteRequiredLine(line)).length,
    [bomLines],
  );

  const canSubmit = design?.status === 'draft' || design?.status === 'reviewed';

  // Build per-item lookup from managed services data
  // Handle both camelCase (from dedicated API) and snake_case (from inline detail)
  const msDeviceMap = useMemo(() => {
    const map = new Map<string, ManagedServiceDeviceEntry & { group: string; groupEnabled: boolean }>();
    if (!msData?.categories) return map;
    for (const cat of msData.categories) {
      for (const raw of (cat.devices || []) as any[]) {
        const device: ManagedServiceDeviceEntry = {
          itemId: raw.itemId || raw.item_id,
          name: raw.name,
          sku: raw.sku,
          category: raw.category,
          quantity: raw.quantity,
          managedServicePrice: raw.managedServicePrice ?? raw.managed_service_price ?? 0,
          excluded: raw.excluded ?? false,
        };
        if (device.itemId) {
          map.set(device.itemId, { ...device, group: cat.group, groupEnabled: cat.enabled !== false });
        }
      }
    }
    return map;
  }, [msData]);

  const msTotalMonthly = msData?.grandTotalMonthly ?? 0;

  const toggleMsForDevice = async (itemId: string, currentlyExcluded: boolean) => {
    if (!accessToken || !designId || !msData) return;
    const config = msData.config || {};
    const enabledSet = new Set<string>((config as any).enabled_categories || (config as any).enabledCategories || []);
    const excludedSet = new Set<string>((config as any).excluded_item_ids || (config as any).excludedItemIds || []);

    // Auto-enable the device's category group if not already enabled
    const deviceInfo = msDeviceMap.get(itemId);
    if (deviceInfo && !enabledSet.has(deviceInfo.group)) {
      enabledSet.add(deviceInfo.group);
    }

    if (currentlyExcluded) {
      excludedSet.delete(itemId);
    } else {
      excludedSet.add(itemId);
    }

    // Optimistic update — flip the device locally so only the toggled row changes
    setMsData((prev) => {
      if (!prev) return prev;
      const newExcluded = !currentlyExcluded;
      return {
        ...prev,
        categories: prev.categories.map((cat) => ({
          ...cat,
          enabled: enabledSet.has(cat.group),
          devices: cat.devices.map((d) =>
            d.itemId === itemId ? { ...d, excluded: newExcluded } : d
          ),
          appliedCount: cat.devices.reduce((sum, d) => {
            const exc = d.itemId === itemId ? newExcluded : d.excluded;
            return sum + (exc ? 0 : d.quantity);
          }, 0),
          excludedCount: cat.devices.reduce((sum, d) => {
            const exc = d.itemId === itemId ? newExcluded : d.excluded;
            return sum + (exc ? d.quantity : 0);
          }, 0),
          monthlyTotal: cat.devices.reduce((sum, d) => {
            const exc = d.itemId === itemId ? newExcluded : d.excluded;
            return sum + (exc ? 0 : d.managedServicePrice * d.quantity);
          }, 0),
        })),
      };
    });

    // Sync with backend in the background (no msSaving spinner to avoid blink)
    try {
      const result = await commerceApi.updateDesignManagedServices(accessToken, designId, {
        enabledCategories: [...enabledSet],
        excludedItemIds: [...excludedSet],
      });
      // Reconcile server truth for the grand total
      setMsData(result);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to update managed service');
      // Revert on error
      loadManagedServices();
    }
  };

  const activeStepIndex = useMemo(() => {
    if (!design) return 0;
    const index = STATUS_FLOW.indexOf(design.status);
    return index < 0 ? 0 : index;
  }, [design?.status]);

  const statusHistory: DesignStatusHistoryEntry[] = useMemo(
    () => (Array.isArray(design?.statusHistory) ? design.statusHistory : []),
    [design?.statusHistory],
  );

  const updates: DesignUpdate[] = useMemo(
    () => (Array.isArray(design?.updates) ? design.updates : []),
    [design?.updates],
  );

  const onSubmitDesign = async () => {
    if (!accessToken || !design) return;
    if (!lead.fullName || !lead.email || !lead.companyName) {
      setError('Full name, email, and company are required for submission.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const updated = await commerceApi.submitNetworkDesign(accessToken, design.id, {
        lead: {
          fullName: lead.fullName,
          email: lead.email,
          companyName: lead.companyName,
          phone: lead.phone || undefined,
          notes: lead.notes || undefined,
        },
      });
      setDesign(updated);
      setNotice('Design submitted successfully.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to submit design');
    } finally {
      setSubmitting(false);
    }
  };

  const onSaveInstallAssistance = async () => {
    if (!accessToken || !design) return;
    setSavingInstall(true);
    setError('');
    try {
      const updated = await commerceApi.updateNetworkDesignInstallAssistance(accessToken, design.id, {
        installMode: installAssistance.installMode || undefined,
        preferredInstallDate: installAssistance.preferredInstallDate || undefined,
        installNotes: installAssistance.installNotes || undefined,
      });
      setDesign(updated);
      setNotice('Installation preference saved.');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to save installation preference');
    } finally {
      setSavingInstall(false);
    }
  };

  return (
    <section className="content-wrap fade-in">
      <div className="content-head row-between">
        <div>
          <h1>Request Status Detail</h1>
          <p className="lead">Track progress from submission through fulfillment and installation in one place.</p>
        </div>
        <Link to="/shop/designs" className="ghost-link">Back to Design History</Link>
      </div>

      {loading && <div className="mini-note">Loading design...</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      {design && (
        <section className="dashboard-grid">
          <article className="dashboard-panel">
            <h3>Request Summary</h3>
            <p className="mini-note">{design.designName || `Design ${design.id.slice(0, 8)}`}</p>
            <p className="mini-note">Status: <span className="badge">{formatStatus(design.status)}</span></p>
            <p className="mini-note">Last Updated: {formatDate(design.statusUpdatedAt || design.updatedAt)}</p>
            {design.quoteId && <p className="mini-note">Quote: {design.quoteId.slice(0, 8).toUpperCase()}</p>}
            {design.orderId && <p className="mini-note">Order: {design.orderId.slice(0, 8).toUpperCase()}</p>}
            <div className="dashboard-kpi-grid">
              <div>
                <span>Estimated CapEx</span>
                <strong>{formatCurrency(design.estimatedCapex)}</strong>
              </div>
              <div>
                <span>AP Count</span>
                <strong>{design.apCount}</strong>
              </div>
              <div>
                <span>Switch Count</span>
                <strong>{design.switchCount}</strong>
              </div>
            </div>
            <div className="dashboard-link-row">
              <button className="ghost-btn" onClick={() => navigate('/shop/designs')}>View History</button>
              {design.quoteId && (
                <button className="ghost-btn" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                  Open Quote
                </button>
              )}
              {design.orderId && (
                <button className="ghost-btn" onClick={() => navigate(`/shop/orders/${design.orderId}`)}>
                  Open Order
                </button>
              )}
              <button className="ghost-btn" onClick={() => document.getElementById('design-bom')?.scrollIntoView({ behavior: 'smooth' })}>
                View BOM
              </button>
              <button className="ghost-btn" onClick={() => document.getElementById('design-diagram')?.scrollIntoView({ behavior: 'smooth' })}>
                View Diagram
              </button>
            </div>
          </article>

          <article className="dashboard-panel">
            <h3>Current Status</h3>
            <p className="mini-note">Submitted: {formatDate(design.submittedAt)}</p>
            <p className="mini-note">Next milestone: {design.nextMilestone || '-'}</p>
            <div className="status-track design-status-track">
              {STATUS_FLOW.map((step, index) => {
                const stateClass = index < activeStepIndex ? 'done' : index === activeStepIndex ? 'active' : '';
                return (
                  <div key={step} className={`track-step ${stateClass}`}>
                    <span className="dot" />
                    <span>{formatStatus(step)}</span>
                  </div>
                );
              })}
            </div>
          </article>

          <article className="dashboard-panel full-width">
            <h3>Progress Timeline</h3>
            <ul className="plain-bullets">
              {statusHistory.map((entry) => (
                <li key={`${entry.changedAt}-${entry.status}`}>
                  <strong>{formatStatus(entry.status)}</strong> · {formatDate(entry.changedAt)}
                  {entry.changedBy ? ` · ${entry.changedBy}` : ''}
                  {entry.note ? ` · ${entry.note}` : ''}
                </li>
              ))}
              {statusHistory.length === 0 && <li>No status updates yet.</li>}
            </ul>
          </article>

          <article className="dashboard-panel">
            <h3>Estimated Milestones</h3>
            <ul className="plain-bullets">
              <li>Review: {formatDate(design.milestones?.estimatedReviewDate)}</li>
              <li>Proposal: {formatDate(design.milestones?.estimatedProposalDate)}</li>
              <li>Fulfillment: {formatDate(design.milestones?.estimatedFulfillmentDate)}</li>
              <li>Installation: {formatDate(design.milestones?.estimatedInstallationDate)}</li>
            </ul>
          </article>

          <article className="dashboard-panel">
            <h3>Confirmed Milestones</h3>
            <ul className="plain-bullets">
              <li>Fulfillment: {formatDate(design.milestones?.confirmedFulfillmentDate)}</li>
              <li>Installation: {formatDate(design.milestones?.confirmedInstallationDate)}</li>
            </ul>
          </article>

          <article className="dashboard-panel full-width">
            <h3>Latest Updates</h3>
            <ul className="plain-bullets">
              {updates.map((update) => (
                <li key={update.id}>
                  <strong>{update.visibility === 'customer' ? 'Customer Update' : 'Internal Update'}</strong>
                  {` · ${formatDate(update.createdAt)} · ${update.message}`}
                </li>
              ))}
              {updates.length === 0 && <li>No updates yet.</li>}
            </ul>
          </article>

          <article className="dashboard-panel">
            <h3>Contact / Lead</h3>
            <div className="onboarding-input-grid">
              <label>
                Full Name
                <input value={lead.fullName} onChange={(e) => setLead((prev) => ({ ...prev, fullName: e.target.value }))} />
              </label>
              <label>
                Email
                <input value={lead.email} onChange={(e) => setLead((prev) => ({ ...prev, email: e.target.value }))} />
              </label>
              <label>
                Company Name
                <input value={lead.companyName} onChange={(e) => setLead((prev) => ({ ...prev, companyName: e.target.value }))} />
              </label>
              <label>
                Phone
                <input value={lead.phone} onChange={(e) => setLead((prev) => ({ ...prev, phone: e.target.value }))} />
              </label>
              <label>
                Notes
                <input value={lead.notes} onChange={(e) => setLead((prev) => ({ ...prev, notes: e.target.value }))} />
              </label>
            </div>
            {canSubmit && (
              <button className="primary-btn" onClick={onSubmitDesign} disabled={submitting}>
                {submitting ? 'Submitting...' : 'Submit Design Request'}
              </button>
            )}
          </article>

          <article className="dashboard-panel">
            <h3>Deployment / Installation</h3>
            <div className="onboarding-input-grid">
              <label>
                Install Mode
                <select
                  value={installAssistance.installMode || 'self_install'}
                  onChange={(e) =>
                    setInstallAssistance((prev) => ({ ...prev, installMode: e.target.value as DesignInstallAssistance['installMode'] }))
                  }
                >
                  <option value="self_install">Self-install</option>
                  <option value="remote_assistance">Remote/video assistance</option>
                  <option value="onsite_visit">Onsite technician visit</option>
                </select>
              </label>
              <label>
                Preferred Install Date
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
            <button className="secondary-btn" onClick={onSaveInstallAssistance} disabled={savingInstall}>
              {savingInstall ? 'Saving...' : 'Save Install Preference'}
            </button>
          </article>

          <article className="dashboard-panel full-width" id="design-diagram">
            <h3>Diagram / Topology Reference</h3>
            <p className="mini-note">
              Topology lines represent connectivity relationships rather than literal cable routing paths:
              Wired link, Wireless link, and Managed connection.
            </p>
            <div className="integration-grid">
              <div className="integration-card">
                <div className="row-between">
                  <strong>Topology Nodes</strong>
                  <span className="badge">{(design.topology?.nodes || []).length || 0}</span>
                </div>
              </div>
              <div className="integration-card">
                <div className="row-between">
                  <strong>Topology Edges</strong>
                  <span className="badge">{(design.topology?.edges || []).length || 0}</span>
                </div>
              </div>
            </div>
            {Array.isArray(design.assumptions) && design.assumptions.length > 0 && (
              <ul className="plain-bullets">
                {design.assumptions.map((note, index) => (
                  <li key={`${index}-${note}`}>{note}</li>
                ))}
              </ul>
            )}
            {design.drawioXml && (
              <DrawioDiagramViewer
                xml={design.drawioXml}
                title={`${design.designName || 'Network Design'} Diagram`}
                initialHeight={700}
              />
            )}
          </article>

          <article className="dashboard-panel full-width" id="design-bom">
            <h3>Equipment / BOM Snapshot</h3>
            {quoteRequiredCount > 0 && (
              <p className="mini-note">
                {quoteRequiredCount} line{quoteRequiredCount > 1 ? 's are' : ' is'} price-on-request pending final quote.
              </p>
            )}
            <table className="cart-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Category</th>
                  <th>Qty</th>
                  <th>Unit Price</th>
                  <th>Total</th>
                  <th>Managed Service</th>
                </tr>
              </thead>
              <tbody>
                {bomLines.map((line) => {
                  const msDevice = line.item_id ? msDeviceMap.get(line.item_id) : undefined;
                  const hasMsPrice = msDevice && msDevice.managedServicePrice > 0;
                  const msIncluded = hasMsPrice && msDevice.groupEnabled && !msDevice.excluded;
                  return (
                    <tr key={line.line_id}>
                      <td>
                        <div>{line.name}</div>
                        {(line.connectivity || line.cable_type) && (
                          <div className="mini-note">
                            {line.cable_type && line.cable_length_meters
                              ? `${line.cable_type} • ${Math.round(line.cable_length_meters)}m estimated • $${Number(line.price_per_meter || 0).toFixed(2)}/m`
                              : connectivityLabel(line.connectivity)}
                          </div>
                        )}
                      </td>
                      <td>{line.category || '-'}</td>
                      <td>{line.quantity}</td>
                      <td>{formatBomMoney(line, 'unit')}</td>
                      <td>{formatBomMoney(line, 'total')}</td>
                      <td>
                        {hasMsPrice ? (
                          <label className="ms-inline-check">
                            <input
                              type="checkbox"
                              checked={msIncluded}
                              disabled={design.status !== 'draft' && design.status !== 'reviewed'}
                              onChange={() => toggleMsForDevice(msDevice.itemId, !msDevice.excluded ? false : true)}
                            />
                            <span className={msIncluded ? 'ms-inline-price' : 'ms-inline-price ms-inline-excluded'}>
                              ${msDevice.managedServicePrice.toFixed(2)}/mo
                            </span>
                          </label>
                        ) : (
                          <span className="mini-note">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {bomLines.length === 0 && (
                  <tr>
                    <td colSpan={6} className="mini-note">No BOM lines found for this design.</td>
                  </tr>
                )}
              </tbody>
              {msTotalMonthly > 0 && (
                <tfoot>
                  <tr className="ms-total-row">
                    <td colSpan={5} style={{ textAlign: 'right', fontWeight: 600 }}>
                      Total Managed Services
                    </td>
                    <td className="ms-inline-total">
                      {formatCurrency(msTotalMonthly)}/mo
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </article>

        </section>
      )}
    </section>
  );
};
