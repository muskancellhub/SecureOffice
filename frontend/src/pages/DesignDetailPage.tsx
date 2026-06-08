import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  DollarSign,
  Layers,
  MapPin,
  MessageSquare,
  Network,
  Send,
  Server,
  ShoppingCart,
  Trash2,
  Wifi,
} from 'lucide-react';
import * as commerceApi from '../api/commerceApi';
import { DrawioDiagramViewer } from '../components/DrawioDiagramViewer';
import { useAuth } from '../context/AuthContext';
import { extractApiError } from '../utils/extractApiError';
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
  const [addingAllToCart, setAddingAllToCart] = useState(false);

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
      setError(extractApiError(err, 'Failed to load design details'));
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

  const orderableLines = useMemo(() => bomLines.filter((line) => Boolean(line.item_id)), [bomLines]);

  const onAddAllToCart = async () => {
    if (!accessToken) return;
    if (orderableLines.length === 0) { setNotice('No catalog-linked BOM items to add.'); return; }
    setAddingAllToCart(true);
    setError('');
    let ok = 0;
    let fail = 0;
    for (const line of orderableLines) {
      try {
        await commerceApi.addCartLine(accessToken, { catalog_item_id: line.item_id as string, quantity: Math.max(1, line.quantity) });
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    setAddingAllToCart(false);
    if (ok > 0) {
      setNotice(`Added ${ok} BOM item${ok > 1 ? 's' : ''} to cart.`);
      setTimeout(() => navigate('/shop/cart'), 600);
    }
    if (fail > 0) setError(`${fail} item${fail > 1 ? 's' : ''} could not be added to cart.`);
  };

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
      setError(extractApiError(err, 'Failed to update managed service'));
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
      setError(extractApiError(err, 'Failed to delete design'));
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
      setError(extractApiError(err, 'Failed to submit design'));
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
      setError(extractApiError(err, 'Failed to save installation preference'));
    } finally {
      setSavingInstall(false);
    }
  };

  const next = nextActionFor(design?.status);
  const statusTone = design ? STATUS_TONE[design.status] || 'neutral' : 'neutral';
  const designLabel = design ? (design.designName || `Design ${design.id.slice(0, 8)}`) : '';
  const canDelete = design?.status === 'draft' || design?.status === 'reviewed';

  return (
    <section className="content-wrap fade-in dnb-page design-detail-page">
      {loading && !design && <div className="dd-loading">Loading design…</div>}
      {error && <div className="onboarding-alert error">{error}</div>}
      {notice && <div className="toast-notice">{notice}</div>}

      {design && (
        <>
          {/* ── Header ──────────────────────────────────────────────── */}
          <header className="apx-header">
            <div className="apx-header-text">
              <Link to="/shop/designs" className="dnb-back"><ArrowLeft size={15} /> Back to designs</Link>
              <h1>{designLabel}</h1>
              <p className="apx-subtitle">Saved network design — bill of materials and topology.</p>
              <div className="apx-scope">
                <span className={`dnb-status-chip ${statusTone === 'success' ? 'reviewed' : statusTone === 'progress' ? 'reviewed' : 'draft'}`}>
                  {formatStatus(design.status)}
                </span>
                <span className="apx-scope-meta">Updated {formatDate(design.statusUpdatedAt || design.updatedAt)}</span>
                {design.quoteId && (
                  <button type="button" className="dnb-meta-link" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                    Quote {design.quoteId.slice(0, 8).toUpperCase()} <ArrowUpRight size={13} />
                  </button>
                )}
                {design.orderId && (
                  <button type="button" className="dnb-meta-link" onClick={() => navigate(`/shop/orders/${design.orderId}`)}>
                    Order {design.orderId.slice(0, 8).toUpperCase()} <ArrowUpRight size={13} />
                  </button>
                )}
              </div>
            </div>
            <button
              className="apx-add-btn dnb-order-btn"
              onClick={onAddAllToCart}
              disabled={addingAllToCart || orderableLines.length === 0}
            >
              <ShoppingCart size={18} /> {addingAllToCart ? 'Adding…' : 'Order this design'}
            </button>
          </header>

          {/* ── Lifecycle toolbar ───────────────────────────────────── */}
          <div className="dnb-toolbar">
            {canSubmit && (
              <button className="dnb-tool-btn" onClick={onSubmitDesign} disabled={submitting}>
                <Send size={15} /> {submitting ? 'Submitting…' : 'Submit for review'}
              </button>
            )}
            {design.quoteId && (
              <button className="dnb-tool-btn" onClick={() => navigate(`/shop/quotes/${design.quoteId}`)}>
                <ArrowUpRight size={15} /> Open quote
              </button>
            )}
            {design.orderId && (
              <button className="dnb-tool-btn" onClick={() => navigate(`/shop/orders/${design.orderId}`)}>
                <ArrowUpRight size={15} /> View order
              </button>
            )}
          </div>

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

          {/* ── Stats ───────────────────────────────────────────────── */}
          <div className="apx-stats dnb-stats">
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Estimated CapEx</span><span className="apx-stat-icon green"><DollarSign size={16} /></span></div>
              <div className="apx-stat-value">{formatCurrency(design.estimatedCapex)}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Access points</span><span className="apx-stat-icon blue"><Wifi size={16} /></span></div>
              <div className="apx-stat-value">{design.apCount}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>Switches</span><span className="apx-stat-icon violet"><Network size={16} /></span></div>
              <div className="apx-stat-value">{design.switchCount}</div>
            </article>
            <article className="apx-stat">
              <div className="apx-stat-head"><span>{msTotalMonthly > 0 ? 'Managed / mo' : 'BOM lines'}</span><span className="apx-stat-icon amber">{msTotalMonthly > 0 ? <Server size={16} /> : <Layers size={16} />}</span></div>
              <div className="apx-stat-value">{msTotalMonthly > 0 ? formatCurrency(msTotalMonthly) : bomLines.length}</div>
            </article>
          </div>

          {/* ── Diagram — shown first, the main artifact ────────────── */}
          <div className="apx-table-card dnb-diagram-card" id="dd-diagram">
            <div className="dnb-card-head">
              <h3 className="apx-modal-title" style={{ margin: 0 }}>Network diagram</h3>
              <div className="dnb-diagram-meta">
                <span>{(design.topology?.nodes || []).length} nodes</span>
                <span>{(design.topology?.edges || []).length} edges</span>
              </div>
            </div>
            {design.drawioXml ? (
              <DrawioDiagramViewer
                xml={design.drawioXml}
                title={`${design.designName || 'Network Design'} Diagram`}
                initialHeight={640}
              />
            ) : (
              <div className="dnb-diagram-empty">
                <Network size={30} strokeWidth={1.3} />
                <p>No diagram has been generated yet.</p>
              </div>
            )}
          </div>

          {/* ── Bill of materials ───────────────────────────────────── */}
          <div className="apx-table-card dnb-bom-card" id="dd-bom">
            <div className="dnb-card-head">
              <h3 className="apx-modal-title" style={{ margin: 0 }}>Bill of materials</h3>
              {quoteRequiredCount > 0 && <span className="dnb-quote-note">{quoteRequiredCount} price-on-request</span>}
            </div>
            {bomLines.length > 0 ? (
              <table className="dnb-bom">
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Category</th>
                    <th className="dnb-num">Qty</th>
                    <th className="dnb-num">Unit</th>
                    <th className="dnb-num">Total</th>
                    <th className="dnb-num">Managed / mo</th>
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
                          <div className="dnb-bom-name">{line.name}</div>
                          {(line.connectivity || line.cable_type) && (
                            <div className="dnb-bom-sub">
                              {line.cable_type && line.cable_length_meters
                                ? `${line.cable_type} • ${Math.round(line.cable_length_meters)}m • $${Number(line.price_per_meter || 0).toFixed(2)}/m`
                                : connectivityLabel(line.connectivity)}
                            </div>
                          )}
                        </td>
                        <td><span className="dnb-cat-tag">{line.category || '—'}</span></td>
                        <td className="dnb-num">{line.quantity}</td>
                        <td className="dnb-num">{formatBomMoney(line, 'unit')}</td>
                        <td className="dnb-num dnb-total">{formatBomMoney(line, 'total')}</td>
                        <td className="dnb-num">
                          {hasMsPrice ? (
                            <label className="ms-inline-check">
                              <input
                                type="checkbox"
                                checked={msIncluded}
                                disabled={design.status !== 'draft' && design.status !== 'reviewed'}
                                onChange={() => toggleMsForDevice(msDevice.itemId, !msDevice.excluded ? false : true)}
                              />
                              <span className={msIncluded ? 'ms-inline-price' : 'ms-inline-price ms-inline-excluded'}>
                                ${msDevice.managedServicePrice.toFixed(2)}
                              </span>
                            </label>
                          ) : (
                            <span className="dnb-dash">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                {msTotalMonthly > 0 && (
                  <tfoot>
                    <tr className="dnb-bom-foot">
                      <td colSpan={5} className="dnb-num">Total managed services</td>
                      <td className="dnb-num dnb-total">{formatCurrency(msTotalMonthly)}/mo</td>
                    </tr>
                  </tfoot>
                )}
              </table>
            ) : (
              <p className="mini-note">No BOM lines yet.</p>
            )}
          </div>

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
