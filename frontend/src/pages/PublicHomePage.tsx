import { ArrowRight, BadgeCheck, Boxes, ClipboardList, ShieldCheck, Truck } from 'lucide-react';
import { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

const offerCards = [
  {
    title: 'Requirements to Design',
    body: 'Capture your business environment once, then instantly generate BOM and deployment visuals.',
    icon: ClipboardList,
  },
  {
    title: 'Unified Product Catalog',
    body: 'Business-ready hardware bundles for SMB rollout planning and procurement.',
    icon: Boxes,
  },
  {
    title: 'Operations-Ready Output',
    body: 'Quote-ready material list and handoff payloads for fast sales-to-ops execution.',
    icon: Truck,
  },
] as const;

const capabilities = [
  'Business intake with deterministic sizing formulas',
  'Product selection + BOM generation from unified catalog',
  'Visual network diagram preview for customer confidence',
  'Quote/history workflow and lifecycle progress tracking',
];

export const PublicHomePage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [imageMissing, setImageMissing] = useState(false);

  return (
    <section className="content-wrap fade-in intro-home-page marketing-home public-home-page">
      <header className="public-home-nav">
        <div className="left-brand">SecureOffice</div>
        <div className="public-home-nav-actions">
          {!user ? (
            <>
              <Link to="/login" className="ghost-link">Sign In</Link>
              <Link to="/signup" className="primary-btn">Sign Up</Link>
            </>
          ) : (
            <button className="ghost-btn" onClick={() => navigate('/shop/dashboard')}>
              Open Workspace
            </button>
          )}
        </div>
      </header>

      <div className="marketing-hero-grid">
        <div className="marketing-hero-copy">
          <div className="intro-pill">
            <ShieldCheck size={14} />
            <span>SMB Network Solution Builder</span>
          </div>
          <h1>
            Plan your network
            <br />
            and build the full design
          </h1>
          <p>
            Start with a business intake, get a concrete bill of materials, and preview a customer-friendly
            network diagram before ordering.
          </p>
          <div className="marketing-cta-row">
            <button className="primary-btn" onClick={() => navigate('/business-intake')}>
              Build Your Design <ArrowRight size={14} />
            </button>
            <button className="ghost-btn" onClick={() => navigate('/business-intake')}>
              Start Intake Form
            </button>
          </div>
          <div className="marketing-proof-row">
            <span>SMB-focused</span>
            <span>Deterministic sizing</span>
            <span>Visual BOM + diagram</span>
          </div>
        </div>

        <div className="marketing-hero-visual" aria-hidden="true">
          {!imageMissing ? (
            <img
              className="marketing-office-image"
              src="/office-hero-pink.png"
              alt="Business network planning visual"
              onError={() => setImageMissing(true)}
            />
          ) : (
            <div className="marketing-image-placeholder">Add `office-hero-pink.png` to `frontend/public` for the hero visual.</div>
          )}
        </div>
      </div>

      <div className="intro-card-grid marketing-offers-grid">
        {offerCards.map((card) => {
          const Icon = card.icon;
          return (
            <article key={card.title} className="intro-card marketing-offer-card">
              <span className="intro-card-icon"><Icon size={16} /></span>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
            </article>
          );
        })}
      </div>

      <section className="marketing-capability-section">
        <div className="row-between">
          <h2>What You Get</h2>
          <button className="ghost-btn" onClick={() => navigate('/business-intake')}>
            Build
          </button>
        </div>
        <div className="capability-grid">
          {capabilities.map((item) => (
            <div key={item} className="capability-item">
              <BadgeCheck size={14} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </section>
    </section>
  );
};
