import { ArrowRight, BadgeCheck, Boxes, Building2, ClipboardList, LogIn, ShieldCheck, Truck } from 'lucide-react';
import { Suspense, useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import NetworkScene3D from '../components/NetworkScene3D';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';

function Typewriter({ text, speed = 50, delay = 400, pauseMs = 2000 }: { text: string; speed?: number; delay?: number; pauseMs?: number }) {
  const [displayed, setDisplayed] = useState('');
  const [phase, setPhase] = useState<'wait' | 'typing' | 'pause' | 'deleting'>('wait');

  useEffect(() => {
    const timer = setTimeout(() => setPhase('typing'), delay);
    return () => clearTimeout(timer);
  }, [delay]);

  useEffect(() => {
    if (phase === 'wait') return;

    if (phase === 'typing') {
      if (displayed.length >= text.length) {
        const timer = setTimeout(() => setPhase('deleting'), pauseMs);
        return () => clearTimeout(timer);
      }
      const timer = setTimeout(() => setDisplayed(text.slice(0, displayed.length + 1)), speed);
      return () => clearTimeout(timer);
    }

    if (phase === 'deleting') {
      if (displayed.length === 0) {
        const timer = setTimeout(() => setPhase('typing'), 400);
        return () => clearTimeout(timer);
      }
      const timer = setTimeout(() => setDisplayed(displayed.slice(0, -1)), speed / 2);
      return () => clearTimeout(timer);
    }
  }, [phase, displayed, text, speed, pauseMs]);

  return (
    <>
      {displayed}
      <span className="typewriter-cursor">|</span>
    </>
  );
}

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

function useScrollReveal() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('revealed');
          observer.unobserve(el);
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return ref;
}

export const PublicHomePage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const offersRef = useScrollReveal();
  const capabilityRef = useScrollReveal();
  const [intakeModalOpen, setIntakeModalOpen] = useState(false);

  return (
    <section className="content-wrap fade-in intro-home-page marketing-home public-home-page">
      <header className="public-home-nav">
        <div className="left-brand">Secure AI Office</div>
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
            <Typewriter text="Plan your network and build the full design" speed={45} delay={500} />
          </h1>
          <p>
            Start with a business intake, get a concrete bill of materials, and preview a customer-friendly
            network diagram before ordering.
          </p>
          <div className="marketing-cta-row">
            <button className="primary-btn" onClick={() => setIntakeModalOpen(true)}>
              Build Your Design <ArrowRight size={14} />
            </button>
          </div>
          <div className="marketing-proof-row">
            <span>SMB-focused</span>
            <span>Deterministic sizing</span>
            <span>Visual BOM + diagram</span>
          </div>
        </div>

        <div className="marketing-hero-visual" aria-hidden="true">
          <Suspense fallback={
            <div className="marketing-image-placeholder" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 340 }}>
              Loading 3D scene...
            </div>
          }>
            <NetworkScene3D />
          </Suspense>
        </div>
      </div>

      <div ref={offersRef} className="intro-card-grid marketing-offers-grid scroll-reveal">
        {offerCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <article key={card.title} className="intro-card marketing-offer-card" style={{ animationDelay: `${i * 0.12}s` }}>
              <span className="intro-card-icon"><Icon size={16} /></span>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
            </article>
          );
        })}
      </div>

      <section ref={capabilityRef} className="marketing-capability-section scroll-reveal">
        <div className="row-between">
          <h2>What You Get</h2>
          <button className="ghost-btn" onClick={() => setIntakeModalOpen(true)}>
            Build
          </button>
        </div>
        <div className="capability-grid">
          {capabilities.map((item, i) => (
            <div key={item} className="capability-item" style={{ animationDelay: `${0.1 + i * 0.1}s` }}>
              <BadgeCheck size={14} />
              <span>{item}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="vendor-cta-section scroll-reveal">
        <div className="vendor-cta-card">
          <div className="vendor-cta-content">
            <div className="vendor-cta-icon">
              <Building2 size={28} />
            </div>
            <h2>Want to become a vendor?</h2>
            <p>
              Join the CellHub Marketplace and sell your networking products to businesses across the U.S.
              Apply as a vendor to get started.
            </p>
            <div className="vendor-cta-buttons">
              <button className="primary-btn" onClick={() => navigate('/vendor/register')}>
                Apply as Vendor <ArrowRight size={14} />
              </button>
              <button className="ghost-btn" onClick={() => navigate('/vendor/login')}>
                <LogIn size={14} /> Vendor Login
              </button>
            </div>
          </div>
        </div>
      </section>

      <BusinessIntakeModal
        open={intakeModalOpen}
        onClose={() => setIntakeModalOpen(false)}
      />
    </section>
  );
};
