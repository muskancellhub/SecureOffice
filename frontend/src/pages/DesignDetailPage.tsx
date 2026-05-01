import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  Cpu,
  Layers,
  MapPin,
  MessageSquare,
  Network,
  Send,
  Server,
  Trash2,
  Wifi,
} from 'lucide-react';
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
  OnboardingProfile,
} from '../types/commerce';

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

const STATUS_TONE: Record<DesignStatus, 'neutral' | 'progress' | 'success' | 'warning'> = {
  draft: 'neutral',
  reviewed: 'neutral',
  submitted: 'progress',
  in_review: 'progress',
  bom_finalized: 'progress',
  proposal_ready: 'progress',
  approved: 'success',
  order_decomposed: 'progress',
  fulfillment_in_progress: 'progress',
  installation_scheduled: 'progress',
  installed: 'success',
  completed: 'success',
};

type NextAction = {
  label: string;
  description: string;
  cta?: string;
};

const nextActionFor = (status: DesignStatus | undefined): NextAction => {
  switch (status) {
    case 'draft':
    case 'reviewed':
      return {
        label: 'Action needed',
        description: 'Add your contact details below and submit this design for our team to review.',
        cta: 'Submit for Review',
      };
    case 'submitted':
    case 'in_review':
      return {
        label: 'Under review',
        description: 'Our solutions team is validating the bill of materials. You will be notified when the proposal is ready.',
      };
    case 'bom_finalized':
    case 'proposal_ready':
      return {
        label: 'Proposal ready',
        description: 'A formal quote has been prepared. Open the quote to review pricing and accept the proposal.',
      };
    case 'approved':
    case 'order_decomposed':
      return {
        label: 'Approved',
        description: 'Order has been generated. Track fulfillment progress below.',
      };
    case 'fulfillment_in_progress':
      return {
        label: 'Fulfillment in progress',
        description: 'Equipment is being procured and prepared for shipment.',
      };
    case 'installation_scheduled':
      return {
        label: 'Installation scheduled',
        description: 'Your installation is on the calendar. Confirm any onsite details with the operations team.',
      };
    case 'installed':
    case 'completed':
      return {
        label: 'All set',
        description: 'Deployment is complete. Reach out if you need any post-installation support.',
      };
    default:
      return { label: 'In progress', description: 'Tracking progress on this design request.' };
  }
};

const defaultInstallState: DesignInstallAssistance = {
  installMode: 'self_install',
  preferredInstallDate: '',
  installNotes: '',
};

export const DesignDetailPage = () => {
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const { designId } = useParams();
  const [design, setDesign] = useState<NetworkDesignDetail | null>(null);
  const [onboarding, setOnboarding] = useState<OnboardingProfile | null>(null);
  const [installAssistance, setInstallAssistance] = useState<DesignInstallAssistance>(defaultInstallState);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [savingInstall, setSavingInstall] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [msData, setMsData] = useState<ManagedServicesDesignSummary | null>(null);
  const [msSaving, setMsSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const loadDesign = async () => {
    if (!accessToken || !designId) return;
    setLoading(true);
    setError('');
    try {
      const data = await commerceApi.getNetworkDesign(accessToken, designId);
      setDesign(data);
      // Always fetch managed services via dedicated endpoint for freshest data
      loadManagedServices(data.id);
      // Pull contact info from onboarding profile so the user doesn't re-enter it
      try {
        const profile = await commerceApi.getOnboardingProfile(accessToken);
        setOnboarding(profile);
      } catch {
        setOnboarding(null);
      }
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

  const onDeleteDesign = async () => {
    if (!accessToken || !design) return;
    const name = design.designName || `Design ${design.id.slice(0, 8)}`;
    const confirmed = window.confirm(`Delete "${name}"? This cannot be undone.`);
    if (!confirmed) return;
    setDeleting(true);
    setError('');
    try {
      await commerceApi.deleteNetworkDesign(accessToken, design.id);
      navigate('/shop/designs');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to delete design');
      setDeleting(false);
    }
  };

  const onSubmitDesign = async () => {
    if (!accessToken || !design) return;
    // Pull lead info from the design itself first, then from onboarding profile,
    // then fall back to the authenticated user's email.
    const fullName = design.lead?.fullName || onboarding?.admin_name || '';
    const email = design.lead?.email || onboarding?.admin_email || user?.email || '';
    const companyName = design.lead?.companyName || onboarding?.organization_name || '';
    const phone = design.lead?.phone || onboarding?.admin_phone || undefined;
    if (!fullName || !email || !companyName) {
      setError(
        'Your contact info is incomplete. Please complete your account onboarding before submitting this design.',
      );
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const updated = await commerceApi.submitNetworkDesign(accessToken, design.id, {
        lead: {
          fullName,
          email,
          companyName,
          phone,
          notes: design.lead?.notes || undefined,
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

  const next = nextActionFor(design?.status);
  const statusTone = design ? STATUS_TONE[design.status] || 'neutral' : 'neutral';
  const designLabel = design ? (design.designName || `Design ${design.id.slice(0, 8)}`) : '';
  const canDelete = design?.status === 'draft' || design?.status === 'reviewed';

  return (
    <section className="content-wrap fade-in design-detail-page">
      {/* Breadcrumb */}
      <Link to="/shop/designs" className="dd-back-link">
        <ArrowLeft size={14} /> Back to Design History
      </Link>

      {loading && !design && <div className="dd-loading">Loading design…</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      {design && (
        <>
          {/* ── Hero header ─────────────────────────────────────────── */}
          <header className="dd-hero">
            <div className="dd-hero-main">
              <span className="dd-eyebrow">Network Design</span>
              <h1 className="dd-title">{designLabel}</h1>
              <div className="dd-hero-meta">
                <span className={`dd-status-pill dd-tone-${statusTone}`}>
                  <span className="dd-status-dot" />
                  {formatStatus(design.status)}
                </span>
                <span className="dd-meta-sep">·</span>
                <span>Updated {formatDate(design.statusUpdatedAt || design.updatedAt)}</span>
                {design.quoteId && (
                  <>
                    <span className="dd-meta-sep">·</span>
                    <button
                      type="button"
                      className="dd-meta-link"
                      onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}
                    >
                      Quote {design.quoteId.slice(0, 8).toUpperCase()} <ArrowUpRight size={12} />
                    </button>
                  </>
                )}
                {design.orderId && (
                  <>
                    <span className="dd-meta-sep">·</span>
                    <button
                      type="button"
                      className="dd-meta-link"
                      onClick={() => navigate(`/shop/orders/${design.orderId}`)}
                    >
                      Order {design.orderId.slice(0, 8).toUpperCase()} <ArrowUpRight size={12} />
                    </button>
                  </>
                )}
              </div>
            </div>
            <div className="dd-hero-actions">
              {canSubmit && (
                <button className="primary-btn dd-primary-cta" onClick={onSubmitDesign} disabled={submitting}>
                  <Send size={14} /> {submitting ? 'Submitting…' : 'Submit for Review'}
                </button>
              )}
              {design.quoteId && !canSubmit && (
                <button className="primary-btn dd-primary-cta" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                  Open Quote <ArrowUpRight size={14} />
                </button>
              )}
            </div>
          </header>

          {/* ── Next action callout ─────────────────────────────────── */}
          <div className={`dd-callout dd-callout-${statusTone}`}>
            <div className="dd-callout-icon">
              {statusTone === 'success' ? <CheckCircle2 size={18} /> : <CalendarClock size={18} />}
            </div>
            <div className="dd-callout-body">
              <strong>{next.label}</strong>
              <span>{next.description}</span>
            </div>
            {design.nextMilestone && (
              <div className="dd-callout-aside">
                <span className="dd-callout-label">Next milestone</span>
                <strong>{design.nextMilestone}</strong>
              </div>
            )}
          </div>

          {/* ── Diagram ─────────────────────────────────────────────── */}
          <section className="dd-section" id="dd-diagram">
            <div className="dd-section-head">
              <h2><Network size={16} /> Network Diagram</h2>
              <span className="dd-section-sub">
                {(design.topology?.nodes || []).length} node{(design.topology?.nodes || []).length === 1 ? '' : 's'} ·
                {' '}
                {(design.topology?.edges || []).length} link{(design.topology?.edges || []).length === 1 ? '' : 's'}
              </span>
            </div>
            <div className="dd-section-card">
              {design.drawioXml ? (
                <DrawioDiagramViewer
                  xml={design.drawioXml}
                  title={`${design.designName || 'Network Design'} Diagram`}
                  initialHeight={700}
                />
              ) : (
                <p className="dd-empty">No diagram has been generated yet.</p>
              )}
            </div>
          </section>

          {/* ── KPI strip ───────────────────────────────────────────── */}
          <div className="dd-kpi-strip">
            <div className="dd-kpi">
              <div className="dd-kpi-icon"><Layers size={16} /></div>
              <div>
                <span className="dd-kpi-label">Estimated CapEx</span>
                <strong className="dd-kpi-value">{formatCurrency(design.estimatedCapex)}</strong>
              </div>
            </div>
            <div className="dd-kpi">
              <div className="dd-kpi-icon"><Wifi size={16} /></div>
              <div>
                <span className="dd-kpi-label">Access Points</span>
                <strong className="dd-kpi-value">{design.apCount}</strong>
              </div>
            </div>
            <div className="dd-kpi">
              <div className="dd-kpi-icon"><Network size={16} /></div>
              <div>
                <span className="dd-kpi-label">Switches</span>
                <strong className="dd-kpi-value">{design.switchCount}</strong>
              </div>
            </div>
            {msTotalMonthly > 0 && (
              <div className="dd-kpi">
                <div className="dd-kpi-icon"><Server size={16} /></div>
                <div>
                  <span className="dd-kpi-label">Managed Services</span>
                  <strong className="dd-kpi-value">{formatCurrency(msTotalMonthly)}<small>/mo</small></strong>
                </div>
              </div>
            )}
          </div>

          {/* ── In-page nav ─────────────────────────────────────────── */}
          <nav className="dd-section-nav">
            <a href="#dd-progress">Progress</a>
            <a href="#dd-bom">Equipment</a>
            <a href="#dd-diagram">Diagram</a>
            <a href="#dd-installation">Installation</a>
          </nav>

          {/* ── Progress section ────────────────────────────────────── */}
          <section className="dd-section" id="dd-progress">
            <div className="dd-section-head">
              <h2>Progress</h2>
              <span className="dd-section-sub">Where this design is in the lifecycle</span>
            </div>
            <div className="dd-progress-card">
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
              <div className="dd-milestone-grid">
                <div>
                  <span className="dd-milestone-label">Submitted</span>
                  <strong>{formatDate(design.submittedAt)}</strong>
                </div>
                <div>
                  <span className="dd-milestone-label">Estimated Review</span>
                  <strong>{formatDate(design.milestones?.estimatedReviewDate)}</strong>
                </div>
                <div>
                  <span className="dd-milestone-label">Estimated Proposal</span>
                  <strong>{formatDate(design.milestones?.estimatedProposalDate)}</strong>
                </div>
                <div>
                  <span className="dd-milestone-label">Estimated Fulfillment</span>
                  <strong>{formatDate(design.milestones?.estimatedFulfillmentDate)}</strong>
                </div>
                <div>
                  <span className="dd-milestone-label">Estimated Installation</span>
                  <strong>{formatDate(design.milestones?.estimatedInstallationDate)}</strong>
                </div>
                <div>
                  <span className="dd-milestone-label">Confirmed Installation</span>
                  <strong>{formatDate(design.milestones?.confirmedInstallationDate)}</strong>
                </div>
              </div>
            </div>

            <div className="dd-twin-grid">
              <div className="dd-section-card">
                <h3 className="dd-card-h"><CalendarClock size={14} /> Status Timeline</h3>
                {statusHistory.length === 0 ? (
                  <p className="dd-empty">No status changes recorded yet.</p>
                ) : (
                  <ul className="dd-timeline">
                    {statusHistory.map((entry) => (
                      <li key={`${entry.changedAt}-${entry.status}`}>
                        <div className="dd-timeline-dot" />
                        <div>
                          <strong>{formatStatus(entry.status)}</strong>
                          <div className="dd-timeline-meta">
                            {formatDate(entry.changedAt)}
                            {entry.changedBy ? ` · ${entry.changedBy}` : ''}
                          </div>
                          {entry.note && <div className="dd-timeline-note">{entry.note}</div>}
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div className="dd-section-card">
                <h3 className="dd-card-h"><MessageSquare size={14} /> Latest Updates</h3>
                {updates.length === 0 ? (
                  <p className="dd-empty">No updates from the team yet.</p>
                ) : (
                  <ul className="dd-update-list">
                    {updates.map((update) => (
                      <li key={update.id}>
                        <span className={`dd-update-tag ${update.visibility === 'customer' ? 'customer' : 'internal'}`}>
                          {update.visibility === 'customer' ? 'Customer' : 'Internal'}
                        </span>
                        <div>
                          <p className="dd-update-msg">{update.message}</p>
                          <span className="dd-update-meta">{formatDate(update.createdAt)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </section>

          {/* ── Equipment / BOM ─────────────────────────────────────── */}
          <section className="dd-section" id="dd-bom">
            <div className="dd-section-head">
              <h2><Cpu size={16} /> Equipment & Bill of Materials</h2>
              <span className="dd-section-sub">
                {bomLines.length} line{bomLines.length === 1 ? '' : 's'}
                {quoteRequiredCount > 0 ? ` · ${quoteRequiredCount} price-on-request` : ''}
              </span>
            </div>
            <div className="dd-section-card dd-bom-card">
              <table className="cart-table dd-bom-table">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Category</th>
                    <th className="dd-num">Qty</th>
                    <th className="dd-num">Unit</th>
                    <th className="dd-num">Total</th>
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
                          <div className="dd-bom-name">{line.name}</div>
                          {(line.connectivity || line.cable_type) && (
                            <div className="dd-bom-sub">
                              {line.cable_type && line.cable_length_meters
                                ? `${line.cable_type} • ${Math.round(line.cable_length_meters)}m est. • $${Number(line.price_per_meter || 0).toFixed(2)}/m`
                                : connectivityLabel(line.connectivity)}
                            </div>
                          )}
                        </td>
                        <td>{line.category || '—'}</td>
                        <td className="dd-num">{line.quantity}</td>
                        <td className="dd-num">{formatBomMoney(line, 'unit')}</td>
                        <td className="dd-num">{formatBomMoney(line, 'total')}</td>
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
                            <span className="dd-bom-sub">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {bomLines.length === 0 && (
                    <tr>
                      <td colSpan={6} className="dd-empty">No BOM lines yet.</td>
                    </tr>
                  )}
                </tbody>
                {msTotalMonthly > 0 && (
                  <tfoot>
                    <tr className="ms-total-row">
                      <td colSpan={5} className="dd-bom-total-label">Total Managed Services</td>
                      <td className="ms-inline-total">{formatCurrency(msTotalMonthly)}/mo</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </section>

          {/* ── Installation ────────────────────────────────────────── */}
          <section className="dd-section" id="dd-installation">
            <div className="dd-section-head">
              <h2><MapPin size={16} /> Installation Preference</h2>
              <span className="dd-section-sub">Choose how you'd like the equipment deployed</span>
            </div>
            <div className="dd-section-card">
              <p className="dd-card-help">
                We'll confirm scheduling once the order is approved.
              </p>
              <div className="dd-form-grid">
                <label>
                  <span>Install Mode</span>
                  <select
                    value={installAssistance.installMode || 'self_install'}
                    onChange={(e) =>
                      setInstallAssistance((prev) => ({ ...prev, installMode: e.target.value as DesignInstallAssistance['installMode'] }))
                    }
                  >
                    <option value="self_install">Self-install — we ship, you deploy</option>
                    <option value="remote_assistance">Remote / video assistance</option>
                    <option value="onsite_visit">Onsite technician visit</option>
                  </select>
                </label>
                <label>
                  <span>Preferred Install Date</span>
                  <input
                    type="date"
                    value={installAssistance.preferredInstallDate || ''}
                    onChange={(e) => setInstallAssistance((prev) => ({ ...prev, preferredInstallDate: e.target.value }))}
                  />
                </label>
                <label className="dd-form-full">
                  <span>Install Notes</span>
                  <textarea
                    rows={3}
                    value={installAssistance.installNotes || ''}
                    onChange={(e) => setInstallAssistance((prev) => ({ ...prev, installNotes: e.target.value }))}
                    placeholder="Site access, contact, building hours, etc."
                  />
                </label>
              </div>
              <div className="dd-form-actions">
                <button className="secondary-btn" onClick={onSaveInstallAssistance} disabled={savingInstall}>
                  {savingInstall ? 'Saving…' : 'Save Preference'}
                </button>
              </div>
            </div>
          </section>

          {/* ── Danger zone ─────────────────────────────────────────── */}
          {canDelete && (
            <section className="dd-section">
              <div className="dd-danger-zone">
                <div>
                  <h3><Trash2 size={14} /> Delete this design</h3>
                  <p>
                    Permanently remove this design and its bill of materials. This cannot be undone.
                    Available only while the design is in <strong>Draft</strong> or <strong>Reviewed</strong>.
                  </p>
                </div>
                <button
                  type="button"
                  className="dd-danger-btn"
                  onClick={onDeleteDesign}
                  disabled={deleting}
                >
                  <Trash2 size={14} /> {deleting ? 'Deleting…' : 'Delete Design'}
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </section>
  );
};
