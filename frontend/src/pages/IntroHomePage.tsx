import { ArrowRight, BadgeCheck, Boxes, ClipboardList, LayoutGrid, Package, ShieldCheck, Truck, Wifi, Zap } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

const offerCards = [
  {
    title: 'Requirement to Proposal',
    body: 'Capture office needs, build BOM, and produce BAFO-ready commercial proposals in minutes.',
    icon: ClipboardList,
    accent: '#fde8f4',
    iconColor: '#c01f70',
  },
  {
    title: 'Unified Catalog + Services',
    body: 'Routers, connectivity, phones, and managed support plans under one buying experience.',
    icon: Boxes,
    accent: '#eef3ff',
    iconColor: '#3b6bd5',
  },
  {
    title: 'Order to Fulfillment',
    body: 'Track projected and confirmed delivery updates from supplier handoff to final install.',
    icon: Truck,
    accent: '#eaf7ee',
    iconColor: '#2d7a3f',
  },
] as const;

const stats = [
  { value: '14+', label: 'BOM line types' },
  { value: 'Real-time', label: 'Topology diagram' },
  { value: 'BAFO', label: 'Proposal-ready' },
];

const capabilities = [
  { text: 'Design-led requirement analysis for new and existing customers', icon: ClipboardList },
  { text: 'Bill-of-material orchestration from CDW, managed services, and partner APIs', icon: Boxes },
  { text: 'Default discount + deal incremental discount pricing model', icon: BadgeCheck },
  { text: 'Proposal, acceptance, and quote-to-order conversion workflow', icon: Package },
  { text: 'Contract handoff capability for CLM integrations', icon: LayoutGrid },
  { text: 'Lifecycle visibility across contracts, subscriptions, and assets', icon: Wifi },
];

export const IntroHomePage = () => {
  const navigate = useNavigate();
  const [imageMissing, setImageMissing] = useState(false);

  return (
    <section className="content-wrap fade-in intro-home-page ih-page">
      {/* Hero */}
      <div className="ih-hero">
        <div className="ih-hero-copy">
          <div className="ih-eyebrow">
            <ShieldCheck size={13} />
            <span>Secure AI Office Platform</span>
          </div>
          <h1>
            Build, price, and deliver<br />
            your secure AI office stack
          </h1>
          <p>
            Unify requirement discovery, BOM building, BAFO pricing, contract handoff,
            and fulfillment tracking — without the coordination chaos.
          </p>

          <div className="ih-stats-row">
            {stats.map((s) => (
              <div key={s.label} className="ih-stat">
                <strong>{s.value}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>

          <div className="ih-cta-row">
            <button className="primary-btn ih-cta-primary" onClick={() => navigate('/shop/designs/new')}>
              Build Your Design <ArrowRight size={15} />
            </button>
          </div>

          <div className="ih-proof-row">
            <span><Zap size={11} /> SMB-focused</span>
            <span><BadgeCheck size={11} /> Deterministic sizing</span>
            <span><Wifi size={11} /> Visual BOM + diagram</span>
          </div>
        </div>

        <div className="ih-hero-visual" aria-hidden="true">
          {!imageMissing ? (
            <img
              className="ih-office-img"
              src="/office-hero-pink.png"
              alt="3D office preview"
              onError={() => setImageMissing(true)}
            />
          ) : (
            <div className="ih-visual-placeholder">
              <div className="ih-visual-grid">
                <div className="ih-vis-card ih-vis-card-a">
                  <Wifi size={22} />
                  <span>Network Design</span>
                </div>
                <div className="ih-vis-card ih-vis-card-b">
                  <Package size={22} />
                  <span>Auto BOM</span>
                </div>
                <div className="ih-vis-card ih-vis-card-c">
                  <Boxes size={22} />
                  <span>Catalog</span>
                </div>
                <div className="ih-vis-card ih-vis-card-d">
                  <BadgeCheck size={22} />
                  <span>Proposals</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Offer Cards */}
      <div className="ih-offer-grid">
        {offerCards.map((card) => {
          const Icon = card.icon;
          return (
            <article key={card.title} className="ih-offer-card">
              <div className="ih-offer-icon" style={{ background: card.accent, color: card.iconColor }}>
                <Icon size={18} />
              </div>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
            </article>
          );
        })}
      </div>

      {/* Capabilities */}
      <section className="ih-capabilities">
        <div className="ih-cap-head">
          <h2>Everything We Offer</h2>
          <button className="ghost-btn ih-cap-btn" onClick={() => navigate('/shop/designs/new')}>
            Get started <ArrowRight size={13} />
          </button>
        </div>
        <div className="ih-cap-grid">
          {capabilities.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.text} className="ih-cap-item">
                <div className="ih-cap-icon"><Icon size={14} /></div>
                <span>{item.text}</span>
              </div>
            );
          })}
        </div>
      </section>
    </section>
  );
};
