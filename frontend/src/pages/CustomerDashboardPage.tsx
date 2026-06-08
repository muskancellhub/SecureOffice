import { Activity, ArrowRight, Boxes, CheckCircle2, ChevronRight, CreditCard, Layers, Package, Plus, ShieldCheck, ShoppingCart, Sparkles, Truck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';
import type { BillingOverview, NetworkDesignSummary, OnboardingProfile, OrderSummary, SubscriptionSummary } from '../types/commerce';

const fmt2 = (v: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v || 0);
const fmt0 = (v: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v || 0);

const greet = (): string => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};

const fmtIso = (d?: string | null): string => {
  if (!d) return '—';
  return String(d).slice(0, 10);
};
const prettyStatus = (s: string): string => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

const ORDER_STEPS = [
  { key: 'placed', label: 'Placed', icon: ShoppingCart },
  { key: 'processing', label: 'Processing', icon: Package },
  { key: 'shipped', label: 'Shipped', icon: Truck },
  { key: 'delivered', label: 'Delivered', icon: CheckCircle2 },
];

const orderStepIndex = (status: string): number => {
  const s = (status || '').toUpperCase();
  if (['DELIVERED', 'ACTIVE', 'COMPLETED'].includes(s)) return 3;
  if (s === 'SHIPPED') return 2;
  if (['PROCESSING', 'VENDOR_ORDERED'].includes(s)) return 1;
  return 0;
};

const openAssistant = () => {
  const fab = document.querySelector<HTMLButtonElement>('.chatbot-fab');
  fab?.click();
};

export const CustomerDashboardPage = () => {
  const { accessToken, user } = useAuth();
  const nav = useNavigate();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [subs, setSubs] = useState<SubscriptionSummary[]>([]);
  const [designs, setDesigns] = useState<NetworkDesignSummary[]>([]);
  const [billing, setBilling] = useState<BillingOverview | null>(null);
  const [profile, setProfile] = useState<OnboardingProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [intakeOpen, setIntakeOpen] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true); setError('');
    Promise.allSettled([
      commerceApi.listOrders(accessToken),
      commerceApi.listSubscriptions(accessToken),
      commerceApi.getBillingOverview(accessToken),
      commerceApi.listNetworkDesigns(accessToken),
      commerceApi.getOnboardingProfile(accessToken),
    ]).then(([oR, sR, bR, dR, pR]) => {
      setOrders(oR.status === 'fulfilled' ? oR.value : []);
      setSubs(sR.status === 'fulfilled' ? sR.value : []);
      setBilling(bR.status === 'fulfilled' ? bR.value : null);
      setDesigns(dR.status === 'fulfilled' ? dR.value : []);
      setProfile(pR.status === 'fulfilled' ? pR.value : null);
      if ([oR, sR, bR, dR].every((r) => r.status === 'rejected')) setError('Failed to load dashboard data');
    }).finally(() => setLoading(false));
  }, [accessToken]);

  const latest = useMemo(
    () => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] || null,
    [orders],
  );
  const activeOrders = useMemo(
    () => orders.filter((o) => !['DELIVERED', 'ACTIVE', 'COMPLETED', 'CANCELLED'].includes((o.status || '').toUpperCase())).length,
    [orders],
  );
  const actSubs = useMemo(() => subs.filter((s) => s.status === 'ACTIVE'), [subs]);
  const subTotal = useMemo(() => actSubs.reduce((s, x) => s + (x.unit_price || 0) * (x.qty || 1), 0), [actSubs]);
  const nextCharge = useMemo(() => {
    const dates = actSubs.map((s) => s.next_billing_date).filter(Boolean).sort();
    return dates[0] ? fmtIso(dates[0]) : '—';
  }, [actSubs]);
  const monthlySpend = billing?.totals?.current_monthly_recurring || subTotal;

  const name = profile?.admin_name || (user?.email ? user.email.split('@')[0] : 'there');
  const orgName = profile?.organization_name || '';
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
  const empty = !loading && orders.length === 0 && designs.length === 0 && subs.length === 0;
  const stepIdx = latest ? orderStepIndex(latest.status) : -1;

  return (
    <section className="content-wrap fade-in dbx-page">
      <div className="dbx-hero">
        <div className="dbx-hero-text">
          <h1>{greet()}, {name}</h1>
          <p>{today}{orgName ? ` · ${orgName}` : ''}</p>
        </div>
        <div className="dbx-hero-actions">
          <button className="dbx-hero-ghost" onClick={() => nav('/shop/routers')}><Boxes size={17} /> Browse catalog</button>
          <button className="dbx-hero-primary" onClick={() => setIntakeOpen(true)}><Plus size={18} /> New design</button>
        </div>
      </div>

      {loading && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {error && <div className="onboarding-alert error">{error}</div>}

      {empty && (
        <article className="dbx-empty">
          <span className="dbx-empty-ico"><Layers size={34} strokeWidth={1.3} /></span>
          <h2>Welcome to Secure AI Office</h2>
          <p>Create your first network design to get started with procurement, quotes, and managed services.</p>
          <button className="dbx-hero-primary" onClick={() => setIntakeOpen(true)}><Plus size={17} /> Create first design</button>
        </article>
      )}

      {!empty && (
        <>
          {/* Stats */}
          <div className="dbx-stats">
            <article className="dbx-stat" role="button" tabIndex={0} onClick={() => nav('/shop/billing')}>
              <div className="dbx-stat-head"><span>Monthly spend</span><span className="dbx-stat-icon pink"><CreditCard size={17} /></span></div>
              <div className="dbx-stat-value">{fmt0(monthlySpend)}</div>
            </article>
            <article className="dbx-stat" role="button" tabIndex={0} onClick={() => nav('/shop/orders')}>
              <div className="dbx-stat-head"><span>Active orders</span><span className="dbx-stat-icon blue"><Package size={17} /></span></div>
              <div className="dbx-stat-value">{activeOrders}</div>
            </article>
            <article className="dbx-stat" role="button" tabIndex={0} onClick={() => nav('/shop/billing')}>
              <div className="dbx-stat-head"><span>Subscriptions</span><span className="dbx-stat-icon green"><Boxes size={17} /></span></div>
              <div className="dbx-stat-value">{actSubs.length}</div>
            </article>
          </div>

          {/* Order in progress + This month */}
          <div className="dbx-row">
            <article className="dbx-card">
              <div className="dbx-card-head">
                <h3><Truck size={17} /> Order in progress</h3>
                {latest && <button className="dbx-card-link" onClick={() => nav(`/shop/orders/${latest.id}`)}>Details <ChevronRight size={14} /></button>}
              </div>
              {!latest ? (
                <div className="dbx-card-empty">
                  <span>No orders yet</span>
                  <button className="dbx-inline-cta" onClick={() => setIntakeOpen(true)}>Create design <ArrowRight size={13} /></button>
                </div>
              ) : (
                <>
                  <div className="dbx-order-top">
                    <span className="dbx-order-id">{latest.public_id}</span>
                    <span className={`dbx-order-status s${stepIdx}`}>{prettyStatus(latest.status)}</span>
                    <span className="dbx-order-placed">placed {fmtIso(latest.created_at)}</span>
                  </div>
                  <div className="dbx-track">
                    {ORDER_STEPS.map((step, i) => {
                      const Icon = step.icon;
                      const state = i < stepIdx ? 'done' : i === stepIdx ? 'active' : '';
                      return (
                        <div key={step.key} className={`dbx-track-step ${state}`}>
                          <span className="dbx-track-ico"><Icon size={17} /></span>
                          <span className="dbx-track-lbl">{step.label}</span>
                          {i < ORDER_STEPS.length - 1 && <span className="dbx-track-line" />}
                        </div>
                      );
                    })}
                  </div>
                  <div className="dbx-order-foot">
                    <span className="dbx-order-eta"><Truck size={15} /> Est. delivery {fmtIso(latest.estimated_delivery_date)}</span>
                  </div>
                </>
              )}
            </article>

            <article className="dbx-card">
              <div className="dbx-card-head">
                <h3><CreditCard size={17} /> This month</h3>
                <button className="dbx-card-link" onClick={() => nav('/shop/billing')}>Billing <ChevronRight size={14} /></button>
              </div>
              <div className="dbx-month-total">
                <span>Recurring total</span>
                <strong>{fmt2(subTotal)}</strong>
              </div>
              {actSubs.length === 0 ? (
                <p className="dbx-card-empty"><span>No active subscriptions</span></p>
              ) : (
                <ul className="dbx-sub-list">
                  {actSubs.slice(0, 4).map((s) => (
                    <li key={s.id}><span>{s.name}</span><strong>{fmt2(s.unit_price * (s.qty || 1))}</strong></li>
                  ))}
                </ul>
              )}
              <div className="dbx-month-next"><Activity size={14} /> Next charge {nextCharge}</div>
            </article>
          </div>

          {/* Quick actions + Ask us */}
          <div className="dbx-row">
            <article className="dbx-card dbx-qa-card">
              <div className="dbx-card-head"><h3><Sparkles size={17} /> Quick actions</h3></div>
              <div className="dbx-qa-grid">
                <button className="dbx-qa-btn pink" onClick={() => setIntakeOpen(true)}><Plus size={20} /><span>New design</span></button>
                <button className="dbx-qa-btn" onClick={() => nav('/shop/services')}><ShieldCheck size={20} /><span>Managed services</span></button>
                <button className="dbx-qa-btn" onClick={() => nav('/shop/orders')}><Package size={20} /><span>Track orders</span></button>
                <button className="dbx-qa-btn" onClick={() => nav('/shop/billing')}><CreditCard size={20} /><span>Billing</span></button>
              </div>
            </article>

            <article className="dbx-ask">
              <span className="dbx-ask-ico"><Sparkles size={22} /></span>
              <div className="dbx-ask-copy">
                <strong>Ask us</strong>
                <span>Resize a design, explain a BOM, or check an order — just ask.</span>
              </div>
              <button className="dbx-ask-btn" onClick={openAssistant}><Sparkles size={16} /> Start a chat</button>
            </article>
          </div>
        </>
      )}

      <BusinessIntakeModal open={intakeOpen} onClose={() => setIntakeOpen(false)} />
    </section>
  );
};
