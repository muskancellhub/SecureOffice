import { ArrowRight, Boxes, Calendar, ChevronRight, CreditCard, FileText, Layers, Package, Plus, ShoppingCart, TrendingUp, Zap } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { BusinessIntakeModal } from '../components/BusinessIntakeModal';
import type { BillingOverview, CatalogItem, NetworkDesignSummary, OrderSummary, QuoteSummary, SubscriptionSummary } from '../types/commerce';

const fmtK = (v: number): string => {
  if (v >= 10000) return `$${(v / 1000).toFixed(1)}k`;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(v || 0);
};
const fmt2 = (v: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(v || 0);

const stColor: Record<string, string> = {
  ACTIVE: 'db-tag-green', PENDING: 'db-tag-amber', PROCESSING: 'db-tag-blue',
  COMPLETED: 'db-tag-green', DELIVERED: 'db-tag-green', CANCELLED: 'db-tag-red',
  SUBMITTED: 'db-tag-amber', draft: 'db-tag-muted', reviewed: 'db-tag-blue',
  submitted: 'db-tag-amber', approved: 'db-tag-green',
};

const STEPS = ['SUBMITTED', 'PROCESSING', 'DELIVERED'];

const greet = (): string => {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
};

const fmtDate = (d: string): string => {
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? '-' : dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const fmtShort = (d: string): string => {
  const dt = new Date(d);
  return isNaN(dt.getTime()) ? '-' : dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

export const CustomerDashboardPage = () => {
  const { accessToken, user } = useAuth();
  const nav = useNavigate();
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [quotes, setQuotes] = useState<QuoteSummary[]>([]);
  const [subs, setSubs] = useState<SubscriptionSummary[]>([]);
  const [designs, setDesigns] = useState<NetworkDesignSummary[]>([]);
  const [billing, setBilling] = useState<BillingOverview | null>(null);
  const [services, setServices] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [intakeOpen, setIntakeOpen] = useState(false);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true); setError('');
    Promise.allSettled([
      commerceApi.listQuotes(accessToken), commerceApi.listOrders(accessToken),
      commerceApi.listSubscriptions(accessToken), commerceApi.getBillingOverview(accessToken),
      commerceApi.getCatalog(accessToken, { type: 'SERVICE', sort: 'price_low' }),
      commerceApi.listNetworkDesigns(accessToken),
    ]).then(([qR, oR, sR, bR, svR, dR]) => {
      setQuotes(qR.status === 'fulfilled' ? qR.value : []);
      setOrders(oR.status === 'fulfilled' ? oR.value : []);
      setSubs(sR.status === 'fulfilled' ? sR.value : []);
      setBilling(bR.status === 'fulfilled' ? bR.value : null);
      setServices(svR.status === 'fulfilled' ? svR.value : []);
      setDesigns(dR.status === 'fulfilled' ? dR.value : []);
      if ([qR, oR, sR, bR, svR, dR].every(r => r.status === 'rejected')) setError('Failed to load dashboard data');
    }).finally(() => setLoading(false));
  }, [accessToken]);

  const latest = useMemo(() => [...orders].sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] || null, [orders]);
  const bill = billing?.totals?.current_monthly_recurring || 0;
  const proj12 = billing?.totals?.projected_next_12_months || 0;
  const actSubs = subs.filter(s => s.status === 'ACTIVE');
  const name = user?.name || (user?.email ? user.email.split('@')[0] : 'there');
  const stepIdx = useMemo(() => {
    if (!latest) return -1;
    const s = (latest.status || '').toUpperCase();
    const i = STEPS.indexOf(s);
    return i >= 0 ? i : (s === 'COMPLETED' || s === 'DELIVERED') ? STEPS.length - 1 : 0;
  }, [latest]);
  const subTotal = useMemo(() => actSubs.reduce((s, x) => s + (x.unit_price || 0) * (x.qty || 1), 0), [actSubs]);
  const empty = !loading && orders.length === 0 && designs.length === 0 && subs.length === 0;
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  return (
    <section className="content-wrap fade-in db-page">
      {/* HERO */}
      <div className="db-hero">
        <div className="db-hero-bg">
          <svg className="db-hero-svg" viewBox="0 0 900 200" preserveAspectRatio="xMidYMid slice">
            <defs>
              <radialGradient id="dg1" cx="50%" cy="50%" r="50%"><stop offset="0%" stopColor="rgba(225,6,125,0.18)" /><stop offset="100%" stopColor="transparent" /></radialGradient>
              <radialGradient id="dg2" cx="50%" cy="50%" r="50%"><stop offset="0%" stopColor="rgba(225,6,125,0.1)" /><stop offset="100%" stopColor="transparent" /></radialGradient>
            </defs>
            <circle cx="140" cy="70" r="130" fill="url(#dg1)" /><circle cx="700" cy="110" r="110" fill="url(#dg2)" />
            {[[100,40],[200,80],[310,50],[400,120],[520,70],[600,130],[700,55],[180,140],[450,40],[650,160],[80,120],[350,150],[550,35],[720,100],[250,30],[160,100],[470,150],[780,80]].map(([cx,cy],i) => <circle key={`d${i}`} cx={cx} cy={cy} r="1.8" fill="rgba(255,255,255,0.3)" />)}
            {[[[100,40],[200,80]],[[200,80],[310,50]],[[310,50],[400,120]],[[400,120],[520,70]],[[520,70],[600,130]],[[600,130],[700,55]],[[180,140],[310,50]],[[450,40],[520,70]],[[80,120],[200,80]],[[350,150],[400,120]],[[550,35],[650,160]],[[650,160],[720,100]],[[250,30],[310,50]],[[160,100],[200,80]],[[470,150],[520,70]],[[780,80],[720,100]]].map(([[x1,y1],[x2,y2]],i) => <line key={`l${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />)}
          </svg>
        </div>
        <div className="db-hero-content">
          <span className="db-hero-tag">Dashboard</span>
          <h1>{greet()}, {name}</h1>
          <p>{today}</p>
          <button className="db-hero-cta" onClick={() => setIntakeOpen(true)}><Plus size={14} /> New Design</button>
        </div>
      </div>

      {loading && <div className="dh-loading-bar"><div className="dh-loading-bar-inner" /></div>}
      {error && <div className="onboarding-alert error">{error}</div>}

      {empty && (
        <article className="db-empty-state">
          <div className="db-empty-glow" />
          <Layers size={40} strokeWidth={1.2} className="db-empty-ico" />
          <h2>Welcome to Secure AI Office</h2>
          <p>Create your first network design to get started with procurement, quotes, and managed services.</p>
          <button className="primary-btn" onClick={() => setIntakeOpen(true)}><Plus size={15} /> Create First Design</button>
        </article>
      )}

      {!empty && (
        <div className="db-body">
          {/* KPI ROW */}
          <div className="db-kpis">
            <div className="db-kpi db-kpi-bill" onClick={() => nav('/shop/billing')} role="button" tabIndex={0}>
              <div>
                <span className="db-kpi-lbl">Monthly Recurring</span>
                <strong className="db-kpi-big">{fmtK(bill)}</strong>
                <span className="db-kpi-sub"><TrendingUp size={11} /> {fmtK(proj12)} projected 12-mo</span>
              </div>
              <div className="db-kpi-right">
                <div className="db-kpi-ring"><CreditCard size={20} /></div>
                <ChevronRight size={16} className="db-kpi-arrow" />
              </div>
            </div>
            <div className="db-kpi" onClick={() => nav('/shop/orders')} role="button" tabIndex={0}>
              <div>
                <span className="db-kpi-lbl">Orders</span>
                <strong className="db-kpi-num">{orders.length}</strong>
              </div>
              <div className="db-kpi-right">
                <div className="db-kpi-ring db-kpi-ring-blue"><ShoppingCart size={18} /></div>
                <ChevronRight size={16} className="db-kpi-arrow" />
              </div>
            </div>
            <div className="db-kpi" onClick={() => nav('/shop/lifecycle')} role="button" tabIndex={0}>
              <div>
                <span className="db-kpi-lbl">Active Subs</span>
                <strong className="db-kpi-num">{actSubs.length}</strong>
              </div>
              <div className="db-kpi-right">
                <div className="db-kpi-ring db-kpi-ring-green"><Boxes size={18} /></div>
                <ChevronRight size={16} className="db-kpi-arrow" />
              </div>
            </div>
            <div className="db-kpi" onClick={() => nav('/shop/designs')} role="button" tabIndex={0}>
              <div>
                <span className="db-kpi-lbl">Designs</span>
                <strong className="db-kpi-num">{designs.length}</strong>
              </div>
              <div className="db-kpi-right">
                <div className="db-kpi-ring db-kpi-ring-violet"><FileText size={18} /></div>
                <ChevronRight size={16} className="db-kpi-arrow" />
              </div>
            </div>
          </div>

          {/* MAIN 3-COL */}
          <div className="db-grid3">
            {/* Process Tracking (order timeline) */}
            <article className="db-card">
              <div className="db-card-hd">
                <h3>Process Tracking</h3>
                <button className="db-card-act" onClick={() => nav('/shop/orders')}>All orders <ChevronRight size={13} /></button>
              </div>
              {!latest ? (
                <div className="db-card-empty-sm">
                  <span>No orders yet</span>
                  <button className="db-inline-cta" onClick={() => setIntakeOpen(true)}>Create design <ArrowRight size={11} /></button>
                </div>
              ) : (
                <div className="db-timeline">
                  {(() => {
                    const events = [
                      { date: fmtShort(latest.created_at), label: 'Order placed', desc: `#${latest.public_id || latest.id.slice(0, 8).toUpperCase()}`, done: true },
                      { date: '', label: 'Processing', desc: 'Fulfillment in progress', done: stepIdx >= 1 },
                      { date: latest.estimated_delivery_date ? fmtShort(latest.estimated_delivery_date) : '', label: 'Delivered', desc: 'Shipment complete', done: stepIdx >= 2 },
                    ];
                    return events.map((ev, i) => (
                      <div key={i} className={`db-tl-item ${ev.done ? 'db-tl-done' : ''}`}>
                        <div className="db-tl-left">{ev.date && <span className="db-tl-date">{ev.date}</span>}</div>
                        <div className="db-tl-track">
                          <div className="db-tl-dot" />
                          {i < events.length - 1 && <div className="db-tl-line" />}
                        </div>
                        <div className="db-tl-right">
                          <strong>{ev.label}</strong>
                          <span>{ev.desc}</span>
                        </div>
                      </div>
                    ));
                  })()}
                </div>
              )}
            </article>

            {/* Active Subscriptions */}
            <article className="db-card">
              <div className="db-card-hd">
                <h3>Active Subscriptions</h3>
                <button className="db-card-act" onClick={() => nav('/shop/lifecycle')}>View all <ChevronRight size={13} /></button>
              </div>
              {actSubs.length === 0 ? (
                <div className="db-card-empty-sm">
                  <span>No active subscriptions</span>
                  <button className="db-inline-cta" onClick={() => nav('/shop/services')}>Browse services <ArrowRight size={11} /></button>
                </div>
              ) : (
                <>
                  <div className="db-tbl">
                    <div className="db-tbl-hd"><span>Service</span><span>Qty</span><span>Monthly</span></div>
                    {actSubs.slice(0, 5).map(s => (
                      <div key={s.id} className="db-tbl-row">
                        <span className="db-tbl-name">{s.name}</span>
                        <span className="db-tbl-dim">{s.qty}</span>
                        <span className="db-tbl-bold">{fmt2(s.unit_price * (s.qty || 1))}</span>
                      </div>
                    ))}
                  </div>
                  <div className="db-tbl-foot"><span>Monthly total</span><strong>{fmt2(subTotal)}</strong></div>
                </>
              )}
            </article>

            {/* Quick Actions */}
            <article className="db-card db-card-qa">
              <h3 className="db-qa-title"><Zap size={13} /> Quick Actions</h3>
              <div className="db-qa-grid">
                <button className="db-qa-btn db-qa-pink" onClick={() => setIntakeOpen(true)}>
                  <Plus size={18} />
                  <span>New Design</span>
                </button>
                <button className="db-qa-btn" onClick={() => nav('/shop/services')}>
                  <ShoppingCart size={18} />
                  <span>Services</span>
                </button>
                <button className="db-qa-btn" onClick={() => nav('/shop/orders')}>
                  <Package size={18} />
                  <span>Orders</span>
                </button>
                <button className="db-qa-btn" onClick={() => nav('/shop/lifecycle')}>
                  <Boxes size={18} />
                  <span>Lifecycle</span>
                </button>
              </div>
            </article>
          </div>

          {/* DESIGNS TABLE */}
          <article className="db-card db-card-full">
            <div className="db-card-hd">
              <h3><FileText size={14} /> Recent Designs</h3>
              <button className="db-card-act" onClick={() => nav('/shop/designs')}>View all <ChevronRight size={13} /></button>
            </div>
            {designs.length === 0 ? (
              <div className="db-card-empty-sm db-card-empty-row">
                <FileText size={16} strokeWidth={1.4} />
                <span>No designs yet</span>
                <button className="db-inline-cta" onClick={() => setIntakeOpen(true)}>Create one <ArrowRight size={11} /></button>
              </div>
            ) : (
              <div className="db-tbl">
                <div className="db-tbl-hd db-tbl-4col"><span>Name</span><span>Status</span><span>CapEx</span><span>Date</span></div>
                {designs.slice(0, 5).map(d => (
                  <Link key={d.id} to={`/shop/designs/${d.id}`} className="db-tbl-row db-tbl-4col">
                    <span className="db-tbl-name">{d.designName || d.id.slice(0, 8)}</span>
                    <span><span className={`db-tag ${stColor[d.status] || ''}`}>{d.status}</span></span>
                    <span className="db-tbl-bold">{fmt2(d.estimatedCapex)}</span>
                    <span className="db-tbl-dim">{fmtDate(d.created_at)}</span>
                  </Link>
                ))}
              </div>
            )}
          </article>
        </div>
      )}

      <BusinessIntakeModal open={intakeOpen} onClose={() => setIntakeOpen(false)} />
    </section>
  );
};
