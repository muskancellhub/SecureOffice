import { ArrowRight, Boxes, Building2, Check, ClipboardList, LogIn, ShieldCheck, Smartphone, Star, Truck } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Suspense, lazy, useState, useEffect, useRef } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
// BUG-008: lazy + post-load mount so the continuously-animating WebGL canvas
// can't keep Firefox's load event pending on this marketing page.
const NetworkScene3D = lazy(() => import('../components/NetworkScene3D'));
import { SceneErrorBoundary } from '../components/SceneErrorBoundary';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';

const offerCards = [
  {
    title: 'Requirements → Design',
    body: 'Capture your business environment once. We instantly size the network and generate a BOM and topology.',
    icon: ClipboardList,
    tone: 'pink',
  },
  {
    title: 'Unified Product Catalog',
    body: 'Real SKUs from Meraki, Extreme, InHand & T-Mobile — bundled and priced for SMB rollout.',
    icon: Boxes,
    tone: 'violet',
  },
  {
    title: 'Operations-Ready Output',
    body: 'Quote-ready material lists and handoff payloads for fast sales-to-ops execution.',
    icon: Truck,
    tone: 'green',
  },
] as const;

const steps = [
  { n: '01', title: 'Business intake', body: 'Tell us your space, headcount, devices and throughput needs.' },
  { n: '02', title: 'Deterministic sizing', body: 'Our calculator computes APs, switches, power and failover.' },
  { n: '03', title: 'BOM + topology', body: 'We pick compatible SKUs and draw the network diagram.' },
  { n: '04', title: 'Order & manage', body: 'Add to cart, track the lifecycle, and layer managed services.' },
] as const;

const capabilities = [
  'Business intake with deterministic sizing formulas',
  'Product selection + BOM from a unified vendor catalog',
  'Visual network diagram for customer confidence',
  'Quote / history workflow and lifecycle tracking',
];

const stats = [
  { value: '4 min', label: 'Avg. design time' },
  { value: '12k+', label: 'Vendor SKUs' },
  { value: '98%', label: 'Sizing accuracy' },
  { value: '99.9%', label: 'Managed uptime' },
];

const proofPoints = ['SMB-focused', 'Deterministic sizing', 'Visual BOM + diagram'];

/** Featured "discounted" plans shown on the public landing page. Mirrors the
 * seeded bundle products (app/services/discounted_seed.py); prices are static
 * here since this page is pre-auth (no catalog token). */
const planCards: {
  sku: string; name: string; icon: LucideIcon; subtitle: string; price: string; unit: string;
  features: string[]; bestValue?: boolean;
}[] = [
  {
    sku: 'DISC-POTS-IN-A-BOX',
    name: 'POTS in a Box',
    icon: ShieldCheck,
    subtitle: 'Managed life-safety & emergency comms over T-Mobile 5G + T-Priority.',
    price: '$95',
    unit: 'one-time',
    features: [
      'High-performance POTS gateway',
      'T-Mobile 5G + T-Priority',
      'Integrated battery backup',
      '24×7 managed monitoring',
      'Add Multiline, SIM & managed services',
    ],
    bestValue: true,
  },
  {
    sku: 'DISC-SMB',
    name: 'SMB Office Bundle',
    icon: Boxes,
    subtitle: 'A complete small-office stack — network, Wi-Fi, AI & security in one.',
    price: '$249',
    unit: 'one-time',
    features: [
      'SMB network device',
      'Wi-Fi Access Point (AP) device',
      'AI edge device',
      'Security AI — small office offer',
    ],
  },
  {
    sku: 'DISC-MOBILITY',
    name: 'Mobility',
    icon: Smartphone,
    subtitle: 'Business mobile identity — a dedicated Multiline number with your phone.',
    price: '$20',
    unit: '/mo',
    features: [
      'Multiline business number',
      'BYOD — keep your personal phone private',
      'Voice, SMS/MMS, Teams & WhatsApp',
      'Optional Movius managed service',
    ],
  },
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
      { threshold: 0.15 },
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
  const stepsRef = useScrollReveal();
  const getRef = useScrollReveal();
  const plansRef = useScrollReveal();
  const vendorRef = useScrollReveal();
  const [intakeModalOpen, setIntakeModalOpen] = useState(false);
  // BUG-008: defer the 3D canvas until the page has fired `load`, so the
  // marketing content loads first and the animation loop can't block it.
  const [show3D, setShow3D] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (document.readyState === 'complete') {
      setShow3D(true);
      return;
    }
    const onLoad = () => setShow3D(true);
    window.addEventListener('load', onLoad, { once: true });
    const fallback = window.setTimeout(() => setShow3D(true), 3000);
    return () => {
      window.removeEventListener('load', onLoad);
      window.clearTimeout(fallback);
    };
  }, []);

  const openWorkspace = () => navigate(user ? '/shop/dashboard' : '/login');

  // Stash the chosen plan, then send the user into auth. We drive the post-auth
  // landing through the app's existing redirect plumbing (`?next=` +
  // `secureOfficePostAuthRedirect`) so the signup/OTP flow lands on the CART
  // instead of its default onboarding/design page. ShopProvider then adds the
  // stashed plan to the cart on mount.
  const handleGetPlan = (sku: string) => {
    try {
      window.localStorage.setItem('pendingPlanSku', sku);
      window.localStorage.setItem('secureOfficePostAuthRedirect', '/shop/cart');
    } catch { /* ignore */ }
    navigate(user ? '/shop/cart' : '/signup?next=/shop/cart');
  };

  return (
    <section className="content-wrap fade-in intro-home-page marketing-home public-home-page mh-page">
      <header className="public-home-nav mh-nav">
        <div className="mh-brand">
          <span className="mh-brand-mark"><ShieldCheck size={16} /></span>
          Secure AI Office
        </div>
        <div className="public-home-nav-actions">
          {!user ? (
            <>
              <Link to="/login" className="mh-nav-ghost">Sign In</Link>
              <Link to="/signup" className="mh-nav-primary">Sign Up</Link>
            </>
          ) : (
            <button className="mh-nav-primary" onClick={() => navigate('/shop/dashboard')}>Open Workspace</button>
          )}
        </div>
      </header>

      {/* Hero */}
      <div className="mh-hero">
        <div className="mh-hero-copy">
          <span className="mh-pill"><ShieldCheck size={15} /> SMB Network Solution Builder</span>
          <h1 className="mh-title">
            Plan your network.<br />
            <span className="mh-title-accent">Build the full design.</span>
          </h1>
          <p className="mh-sub">
            Start with a short business intake, get a concrete bill of materials, and preview a
            customer-friendly network diagram — before you order a single device.
          </p>
          <div className="mh-hero-cta">
            <button className="mh-btn-primary" onClick={() => setIntakeModalOpen(true)}>
              Build your design <ArrowRight size={17} />
            </button>
            <button className="mh-btn-outline" onClick={openWorkspace}>Open workspace</button>
          </div>
          <div className="mh-proof">
            {proofPoints.map((point) => (
              <span key={point} className="mh-proof-item"><Check size={15} /> {point}</span>
            ))}
          </div>
        </div>

        <div className="mh-hero-visual" aria-hidden="true">
          <SceneErrorBoundary fallback={
            <div className="marketing-image-placeholder" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 340 }}>
              Network visualization unavailable in this browser.
            </div>
          }>
            <Suspense fallback={
              <div className="marketing-image-placeholder" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 340 }}>
                Loading 3D scene...
              </div>
            }>
              {show3D ? <NetworkScene3D /> : (
                <div className="marketing-image-placeholder" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', minHeight: 340 }}>
                  Loading 3D scene...
                </div>
              )}
            </Suspense>
          </SceneErrorBoundary>
        </div>
      </div>

      {/* Offer cards */}
      <div ref={offersRef} className="mh-offers scroll-reveal">
        {offerCards.map((card, i) => {
          const Icon = card.icon;
          return (
            <article key={card.title} className="mh-offer-card" style={{ animationDelay: `${i * 0.1}s` }}>
              <span className={`mh-offer-icon tone-${card.tone}`}><Icon size={24} /></span>
              <h3>{card.title}</h3>
              <p>{card.body}</p>
            </article>
          );
        })}
      </div>

      {/* Featured discounted plans */}
      <section ref={plansRef} className="ih-plans scroll-reveal">
        <div className="ih-plans-head">
          <h2>Featured plans</h2>
          <p>Our most popular bundles — discounted, ready to deploy.</p>
        </div>
        <div className="ih-plans-grid">
          {planCards.map((card) => {
            const Icon = card.icon;
            return (
              <article key={card.name} className={`ih-plan-card${card.bestValue ? ' best' : ''}`}>
                {card.bestValue && <span className="ih-plan-badge"><Star size={12} /> Best Value</span>}
                <div className="ih-plan-top">
                  <span className="ih-plan-icon"><Icon size={20} /></span>
                  <h3>{card.name}</h3>
                </div>
                <p className="ih-plan-sub">{card.subtitle}</p>
                <div className="ih-plan-price">
                  <strong>{card.price}</strong><span>{card.unit}</span>
                  <span className="ih-plan-tag">Discounted</span>
                </div>
                <ul className="ih-plan-features">
                  {card.features.map((f) => (
                    <li key={f}><Check size={15} /> {f}</li>
                  ))}
                </ul>
                <button className="ih-plan-cta" onClick={() => handleGetPlan(card.sku)}>
                  Get started <ArrowRight size={16} />
                </button>
              </article>
            );
          })}
        </div>
      </section>

      {/* How it works — four steps */}
      <section ref={stepsRef} className="mh-steps-section scroll-reveal">
        <div className="mh-section-head">
          <div>
            <span className="mh-eyebrow">How it works</span>
            <h2>Four steps to a deployed network</h2>
          </div>
          <button className="mh-start-btn" onClick={() => setIntakeModalOpen(true)}>
            Start now <ArrowRight size={16} />
          </button>
        </div>
        <div className="mh-steps">
          {steps.map((step, i) => (
            <article key={step.n} className="mh-step-card" style={{ animationDelay: `${i * 0.08}s` }}>
              <span className="mh-step-num">{step.n}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>
          ))}
        </div>
      </section>

      {/* What you get — dark panel */}
      <section ref={getRef} className="mh-get scroll-reveal">
        <div className="mh-get-left">
          <span className="mh-eyebrow mh-eyebrow-light">What you get</span>
          <h2>Everything from intake to install, in one place.</h2>
          <ul className="mh-get-list">
            {capabilities.map((item) => (
              <li key={item}><span className="mh-get-check"><Check size={13} /></span> {item}</li>
            ))}
          </ul>
        </div>
        <div className="mh-get-stats">
          {stats.map((stat) => (
            <div key={stat.label} className="mh-stat">
              <span className="mh-stat-value">{stat.value}</span>
              <span className="mh-stat-label">{stat.label}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Vendor CTA */}
      <section ref={vendorRef} className="mh-vendor scroll-reveal">
        <span className="mh-vendor-icon"><Building2 size={26} /></span>
        <div className="mh-vendor-copy">
          <h2>Want to become a vendor?</h2>
          <p>Join the CellHub Marketplace and sell networking products to businesses across the U.S.</p>
        </div>
        <div className="mh-vendor-buttons">
          <button className="mh-btn-primary" onClick={() => navigate('/vendor/register')}>
            Apply as vendor <ArrowRight size={16} />
          </button>
          <button className="mh-btn-outline" onClick={() => navigate('/vendor/login')}>
            <LogIn size={16} /> Vendor login
          </button>
        </div>
      </section>

      <BusinessIntakeModal open={intakeModalOpen} onClose={() => setIntakeModalOpen(false)} />
    </section>
  );
};
