import { Activity, ArrowRight, Boxes, ChevronLeft, ChevronRight, CreditCard, Layers, Package, Plus, ShieldCheck, Sparkles, Truck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';
import type { BillingOverview, NetworkDesignSummary, OnboardingProfile, OrderSummary, SubscriptionSummary } from '../types/commerce';

// Always show cents wherever a price is displayed, for consistency across cards.
const fmt2 = (v: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v || 0);

const greet = (): string => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};

const fmtIso = (d?: string | null): string => {
  if (!d) return '—';
  return String(d).slice(0, 10);
};
const prettyStatus = (s: string): string => s.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

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

  // Orders still "in progress" — everything not delivered/completed/cancelled
  // (in-transit "shipped" orders still count), newest first. Same predicate the
  // "Active orders" stat uses, so the count and the carousel always agree.
  const activeOrderList = useMemo(
    () => orders
      .filter((o) => !['DELIVERED', 'ACTIVE', 'COMPLETED', 'CANCELLED'].includes((o.status || '').toUpperCase()))
      .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at)),
    [orders],
  );
  const activeOrders = activeOrderList.length;
  const [orderSlide, setOrderSlide] = useState(0);
  // Keep the carousel index in range as the list loads/changes.
  useEffect(() => {
    setOrderSlide((i) => (activeOrderList.length ? Math.min(i, activeOrderList.length - 1) : 0));
  }, [activeOrderList.length]);
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
  const currentOrder = activeOrderList[Math.min(orderSlide, Math.max(0, activeOrderList.length - 1))];

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
              <div className="dbx-stat-value">{fmt2(monthlySpend)}</div>
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

          {/* Orders in progress (sliding carousel) + This month */}
          <div className="dbx-row">
            <article className="dbx-card dbx-orders-card">
              <div className="dbx-card-head">
                <h3><Truck size={17} /> Orders in progress
                  {activeOrders > 0 && <span className="dbx-orders-count">{activeOrders}</span>}
                </h3>
                {activeOrders > 1 && (
                  <div className="dbx-orders-nav">
                    <button className="dbx-orders-arrow" aria-label="Previous order"
                            onClick={() => setOrderSlide((i) => (i - 1 + activeOrders) % activeOrders)}>
                      <ChevronLeft size={16} />
                    </button>
                    <span className="dbx-orders-pos">{Math.min(orderSlide, activeOrders - 1) + 1}/{activeOrders}</span>
                    <button className="dbx-orders-arrow" aria-label="Next order"
                            onClick={() => setOrderSlide((i) => (i + 1) % activeOrders)}>
                      <ChevronRight size={16} />
                    </button>
                  </div>
                )}
              </div>
              {!currentOrder ? (
                <div className="dbx-card-empty">
                  <span>No orders in progress</span>
                  <button className="dbx-inline-cta" onClick={() => setIntakeOpen(true)}>Create design <ArrowRight size={13} /></button>
                </div>
              ) : (
                <>
                  <div className="dbx-order-slide" role="button" tabIndex={0}
                       onClick={() => nav(`/shop/orders/${currentOrder.id}`)}
                       onKeyDown={(e) => { if (e.key === 'Enter') nav(`/shop/orders/${currentOrder.id}`); }}>
                    <div className="dbx-order-top">
                      <span className="dbx-order-id">{currentOrder.public_id}</span>
                      <span className="dbx-order-status">{prettyStatus(currentOrder.status)}</span>
                    </div>
                    <div className="dbx-order-slide-foot">
                      <span className="dbx-order-placed">Placed {fmtIso(currentOrder.created_at)}</span>
                      <button className="dbx-card-link" onClick={(e) => { e.stopPropagation(); nav(`/shop/orders/${currentOrder.id}`); }}>
                        Details <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>
                  {activeOrders > 1 && (
                    <div className="dbx-orders-dots">
                      {activeOrderList.map((o, i) => (
                        <button key={o.id} aria-label={`Order ${i + 1}`}
                                className={`dbx-orders-dot ${i === Math.min(orderSlide, activeOrders - 1) ? 'active' : ''}`}
                                onClick={() => setOrderSlide(i)} />
                      ))}
                    </div>
                  )}
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
