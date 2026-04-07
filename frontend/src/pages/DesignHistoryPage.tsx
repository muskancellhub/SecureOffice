import { Clock, Eye, FileText, Plus, ReceiptText, ShoppingCart, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { NetworkDesignSummary } from '../types/commerce';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value || 0);

const statusConfig: Record<string, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'badge-draft' },
  reviewed: { label: 'Reviewed', className: 'badge-reviewed' },
  submitted: { label: 'Submitted', className: 'badge-submitted' },
  approved: { label: 'Approved', className: 'badge-approved' },
  rejected: { label: 'Rejected', className: 'badge-rejected' },
};

const getStatusBadge = (status: string) => {
  const cfg = statusConfig[status] || { label: status, className: '' };
  return <span className={`design-status-badge ${cfg.className}`}>{cfg.label}</span>;
};

const formatDate = (dateStr: string): string => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

export const DesignHistoryPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [designs, setDesigns] = useState<NetworkDesignSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    commerceApi.listNetworkDesigns(accessToken)
      .then((rows) => setDesigns(rows))
      .catch((err: any) => setError(err?.response?.data?.detail || 'Failed to load design history'))
      .finally(() => setLoading(false));
  }, [accessToken]);

  const submittedDesigns = useMemo(
    () => designs.filter((row) => row.status !== 'draft' && row.status !== 'reviewed'),
    [designs],
  );

  return (
    <section className="content-wrap fade-in design-history-page">
      <div className="dh-header">
        <div className="dh-header-text">
          <h1>Design History</h1>
          <p className="lead">Manage your network designs, track quotes, and continue from previous configurations.</p>
        </div>
        <button className="primary-btn dh-new-btn" onClick={() => navigate('/shop/designs/new')}>
          <Plus size={16} />
          New Design
        </button>
      </div>

      {loading && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {error && <div className="onboarding-alert error">{error}</div>}

      {!loading && designs.length === 0 && (
        <article className="dh-empty-state">
          <div className="dh-empty-icon"><FileText size={40} strokeWidth={1.2} /></div>
          <h3>No designs yet</h3>
          <p>Create your first network design to get started with automated BOM generation and topology diagrams.</p>
          <button className="primary-btn" onClick={() => navigate('/shop/designs/new')}>Create First Design</button>
        </article>
      )}

      {designs.length > 0 && (
        <div className="dh-grid">
          <div className="dh-main-col">
            <div className="dh-section-label">
              <Clock size={14} />
              Recent Designs
              <span className="dh-count">{designs.length}</span>
            </div>
            <div className="dh-designs-list">
              {designs.map((design) => (
                <article key={design.id} className="dh-design-card">
                  <div className="dh-card-top">
                    <div className="dh-card-title-row">
                      <h4>{design.designName || `Design ${design.id.slice(0, 8)}`}</h4>
                      {getStatusBadge(design.status)}
                    </div>
                    <span className="dh-card-company">{design.lead?.companyName || 'No company'}</span>
                  </div>

                  <div className="dh-card-metrics">
                    <div className="dh-metric">
                      <span className="dh-metric-label">CapEx</span>
                      <span className="dh-metric-value">{formatCurrency(design.estimatedCapex)}</span>
                    </div>
                    <div className="dh-metric">
                      <span className="dh-metric-label">APs</span>
                      <span className="dh-metric-value">{design.apCount}</span>
                    </div>
                    <div className="dh-metric">
                      <span className="dh-metric-label">Switches</span>
                      <span className="dh-metric-value">{design.switchCount}</span>
                    </div>
                    <div className="dh-metric">
                      <span className="dh-metric-label">Created</span>
                      <span className="dh-metric-value">{formatDate(design.createdAt)}</span>
                    </div>
                  </div>

                  {design.nextMilestone && (
                    <div className="dh-milestone">
                      <Zap size={12} />
                      {design.nextMilestone}
                    </div>
                  )}

                  <div className="dh-card-actions">
                    <Link className="dh-action-link" to={`/shop/designs/${design.id}`}>
                      <Eye size={13} /> View Design
                    </Link>
                    {design.quoteId && (
                      <Link className="dh-action-link" to={`/shop/quotes/${design.quoteId}`}>
                        <ReceiptText size={13} /> Quote
                      </Link>
                    )}
                    {design.orderId && (
                      <Link className="dh-action-link" to={`/shop/orders/${design.orderId}`}>
                        <ShoppingCart size={13} /> Order
                      </Link>
                    )}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="dh-side-col">
            <div className="dh-side-card">
              <div className="dh-section-label">
                <FileText size={14} />
                Submitted Requests
              </div>
              {submittedDesigns.length === 0 && (
                <p className="mini-note">No submitted requests yet. Submit a design to start status tracking.</p>
              )}
              <div className="dh-submitted-list">
                {submittedDesigns.slice(0, 6).map((design) => (
                  <Link key={design.id} to={`/shop/designs/${design.id}`} className="dh-submitted-item">
                    <div className="dh-submitted-name">{design.designName || design.id.slice(0, 8)}</div>
                    <div className="dh-submitted-meta">
                      {getStatusBadge(design.status)}
                      <span className="mini-note">{design.lead?.companyName || ''}</span>
                    </div>
                  </Link>
                ))}
              </div>
            </div>

            <div className="dh-side-card">
              <div className="dh-section-label">
                <Zap size={14} />
                Quick Actions
              </div>
              <div className="dh-quick-actions">
                <Link className="dh-quick-link" to="/shop/designs/new">
                  <Plus size={14} /> Generate New Design
                </Link>
                <Link className="dh-quick-link" to="/shop/dashboard">
                  <Eye size={14} /> Back to Dashboard
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
