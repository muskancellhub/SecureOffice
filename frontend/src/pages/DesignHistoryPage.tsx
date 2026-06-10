import { FileText, MapPin, Network, Plus, Search, Trash2, Wifi } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';
import type { NetworkDesignSummary } from '../types/commerce';
import { extractApiError } from '../utils/extractApiError';
import networkDesignImg from '../network_design.png';

const formatCapex = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value || 0);

const formatDate = (dateStr: string): string => {
  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
};

// Placeholder visual shown at the top of every design card.
const CARD_PLACEHOLDER_IMG = networkDesignImg;

export const DesignHistoryPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [designs, setDesigns] = useState<NetworkDesignSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [intakeOpen, setIntakeOpen] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  const onDelete = async (design: NetworkDesignSummary) => {
    if (!accessToken) return;
    const name = design.designName || `Design ${design.id.slice(0, 8)}`;
    const confirmed = window.confirm(`Delete "${name}"? This cannot be undone.`);
    if (!confirmed) return;

    setDeletingId(design.id);
    setError('');
    try {
      await commerceApi.deleteNetworkDesign(accessToken, design.id);
      setDesigns((rows) => rows.filter((r) => r.id !== design.id));
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to delete design'));
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    commerceApi.listNetworkDesigns(accessToken)
      .then((rows) => setDesigns(rows))
      .catch((err: any) => setError(extractApiError(err, 'Failed to load design history')))
      .finally(() => setLoading(false));
  }, [accessToken]);

  const filteredDesigns = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return designs;
    return designs.filter((design) => {
      const name = (design.designName || '').toLowerCase();
      const company = (design.lead?.companyName || '').toLowerCase();
      return name.includes(q) || company.includes(q);
    });
  }, [designs, query]);

  return (
    <section className="content-wrap fade-in network-designs-page">
      <div className="nd-header">
        <div className="nd-header-text">
          <h1>Network designs</h1>
          <p className="nd-subtitle">Every design you've sized, saved, and submitted.</p>
        </div>
        <button className="nd-new-btn" onClick={() => setIntakeOpen(true)}>
          <Plus size={17} />
          New design
        </button>
      </div>

      <div className="nd-toolbar">
        <div className="nd-search">
          <Search size={16} />
          <input
            type="text"
            placeholder="Search designs..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
      </div>

      {loading && <div className="nd-loading-bar"><div className="nd-loading-bar-inner" /></div>}
      {error && <div className="onboarding-alert error">{error}</div>}

      {!loading && designs.length === 0 && (
        <article className="nd-empty-state">
          <div className="nd-empty-icon"><FileText size={40} strokeWidth={1.2} /></div>
          <h3>No designs yet</h3>
          <p>Create your first network design to get started with automated BOM generation and topology diagrams.</p>
          <button className="nd-new-btn" onClick={() => setIntakeOpen(true)}>
            <Plus size={17} /> Create First Design
          </button>
        </article>
      )}

      {!loading && designs.length > 0 && filteredDesigns.length === 0 && (
        <p className="nd-no-match">No designs match this filter.</p>
      )}

      {filteredDesigns.length > 0 && (
        <div className="nd-grid">
          {filteredDesigns.map((design) => {
            return (
              <article
                key={design.id}
                className="nd-card"
                onClick={() => navigate(`/shop/designs/${design.id}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    navigate(`/shop/designs/${design.id}`);
                  }
                }}
              >
                <div className="nd-card-viz">
                  <img className="nd-card-viz-img" src={CARD_PLACEHOLDER_IMG} alt="" aria-hidden="true" loading="lazy" />
                  <button
                    type="button"
                    className="nd-card-delete"
                    title="Delete design"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(design);
                    }}
                    disabled={deletingId === design.id}
                  >
                    <Trash2 size={15} />
                  </button>
                </div>

                <div className="nd-card-body">
                  <div className="nd-card-head">
                    <span className="nd-date">{formatDate(design.createdAt)}</span>
                  </div>

                  <h3 className="nd-card-title">{design.designName || `Design ${design.id.slice(0, 8)}`}</h3>

                  <div className="nd-meta">
                    <span className="nd-meta-item"><Wifi size={15} /> {design.apCount} APs</span>
                    <span className="nd-meta-item"><Network size={15} /> {design.switchCount} sw</span>
                    <span className="nd-meta-item nd-meta-company">
                      <MapPin size={15} /> {design.lead?.companyName || 'No company'}
                    </span>
                  </div>

                  <div className="nd-card-divider" />

                  <div className="nd-capex">
                    <span className="nd-capex-label">Est. CapEx</span>
                    <span className="nd-capex-value">{formatCapex(design.estimatedCapex)}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}

      <BusinessIntakeModal open={intakeOpen} onClose={() => setIntakeOpen(false)} />
    </section>
  );
};
