import { ChevronLeft, ChevronRight, Laptop, LayoutGrid, Minus, Network, Plus, RadioTower, Router as RouterIcon, Search, Server, ShieldCheck, ShoppingCart, Smartphone, Trash2, Wifi } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import BundleConfigurator from '../components/BundleConfigurator';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';
import { extractApiError } from '../utils/extractApiError';

const TABS: { key: string; label: string; cats: string[] | null; icon: LucideIcon }[] = [
  { key: 'all', label: 'All devices', cats: null, icon: LayoutGrid },
  { key: 'network', label: 'Routers & switches', cats: ['router', 'switch', 'wifi_ap', 'firewall', 'security_appliance'], icon: RouterIcon },
  { key: 'compute', label: 'Tablets & laptops', cats: ['laptop', 'tablet'], icon: Laptop },
  { key: 'phone', label: 'Phones', cats: ['phone'], icon: Smartphone },
  { key: 'cellular', label: 'Hotspots & gateways', cats: ['hotspot', 'cellular_gateway'], icon: RadioTower },
];

const PRICE_RANGES: { value: string; label: string; min: number; max: number }[] = [
  { value: '', label: 'Any price', min: 0, max: Infinity },
  { value: '0-500', label: 'Under $500', min: 0, max: 500 },
  { value: '500-2000', label: '$500 – $2,000', min: 500, max: 2000 },
  { value: '2000-5000', label: '$2,000 – $5,000', min: 2000, max: 5000 },
  { value: '5000-', label: '$5,000+', min: 5000, max: Infinity },
];

const SORTS = [
  { value: 'recommended', label: 'Sort: Recommended' },
  { value: 'price_low', label: 'Price: low to high' },
  { value: 'price_high', label: 'Price: high to low' },
  { value: 'availability', label: 'Availability' },
];

const CATEGORY_ICON: Record<string, { icon: LucideIcon; tone: string }> = {
  router: { icon: RouterIcon, tone: 'blue' }, wifi_ap: { icon: Wifi, tone: 'blue' }, switch: { icon: Network, tone: 'blue' },
  firewall: { icon: ShieldCheck, tone: 'blue' }, security_appliance: { icon: ShieldCheck, tone: 'blue' },
  cellular_gateway: { icon: RadioTower, tone: 'amber' }, hotspot: { icon: RadioTower, tone: 'amber' },
  laptop: { icon: Laptop, tone: 'violet' }, tablet: { icon: Laptop, tone: 'violet' }, phone: { icon: Smartphone, tone: 'violet' },
};

const availabilityInfo = (item: CatalogItem): { label: string; tone: string } => {
  const a = (item.availability || 'in_stock').toLowerCase();
  if (a.includes('back')) return { label: 'Backorder', tone: 'amber' };
  if (a.includes('lead')) return { label: 'Lead time', tone: 'amber' };
  return { label: 'In stock', tone: 'green' };
};

const brandOf = (item: CatalogItem): string => String(item.attributes?.brand || item.vendor || '').trim();
const papiImageOf = (item: CatalogItem): string => String(item.attributes?.image_url || '').trim();

export const RoutersCatalogPage = () => {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { cart, addProductToCart, updateLineQuantity, removeLine } = useShop();
  const [searchParams] = useSearchParams();
  const initialTab = TABS.find((t) => t.cats?.includes(searchParams.get('category') || ''))?.key || 'all';

  const [allItems, setAllItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [tab, setTab] = useState(initialTab);
  const [search, setSearch] = useState('');
  const [brand, setBrand] = useState('');
  const [priceRange, setPriceRange] = useState('');
  const [availability, setAvailability] = useState('');
  const [sort, setSort] = useState('recommended');
  const [busyItemId, setBusyItemId] = useState<string | null>(null);
  const [failedImg, setFailedImg] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  // Bundling configurator popup (Phase 7 D9).
  const [configuring, setConfiguring] = useState<CatalogItem | null>(null);
  // Per-card line count for "multiline" items (dropdown → $/line × N).
  const [lineSel, setLineSel] = useState<Record<string, number>>({});
  const PAGE_SIZE = 16;

  const cartLineMap = useMemo(() => {
    const map = new Map<string, { lineId: string; quantity: number }>();
    if (!cart?.lines) return map;
    for (const line of cart.lines) {
      // Component-model carts: track the configured product's parent line.
      if (line.product_id && (line.is_parent || !line.applies_to_line_id)) {
        if (!map.has(line.product_id)) map.set(line.product_id, { lineId: line.id, quantity: line.quantity });
      }
    }
    return map;
  }, [cart]);

  const addMultiline = async (item: CatalogItem, lines: number) => {
    setBusyItemId(item.id);
    try {
      await addProductToCart(item.product_id ?? item.id, { quantity: lines });
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to add to cart'));
    } finally {
      setBusyItemId(null);
    }
  };

  const openConfigurator = async (item: CatalogItem) => {
    if (!accessToken) return;
    setBusyItemId(item.id);
    try {
      // Detail carries the per-tenant priced component rows.
      const detail = await commerceApi.getCatalogItem(accessToken, item.id);
      const active = detail.components ?? [];
      if (active.length > 1) {
        setConfiguring(detail);
      } else {
        // Flat single-component device — no popup needed.
        await addProductToCart(detail.product_id ?? detail.id, { quantity: 1 });
      }
    } catch (err: any) {
      setError(extractApiError(err, 'Failed to load product configuration'));
    } finally {
      setBusyItemId(null);
    }
  };

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    setLoading(true);
    setError('');
    // The backend caps page_size at 250, so page through the full catalog
    // (PAPI + Excel + seeded SKUs) instead of truncating at one page.
    (async () => {
      try {
        // The catalog service caps DEVICE listings at 25 items per page, so we
        // page through the whole catalog (~400 SKUs across PAPI / Excel / CDW)
        // until a page comes back empty instead of stopping after one request.
        const all: CatalogItem[] = [];
        const seen = new Set<string>();
        for (let page = 1; page <= 100; page += 1) {
          const batch = await commerceApi.getCatalog(accessToken, { type: 'DEVICE', sort: 'recommended', page, page_size: 250 });
          if (batch.length === 0) break;
          for (const it of batch) {
            if (!seen.has(it.id)) { seen.add(it.id); all.push(it); }
          }
          if (batch.length < 25) break;
        }
        if (!cancelled) setAllItems(all);
      } catch (err: any) {
        if (!cancelled) setError(extractApiError(err, 'Failed to load catalog'));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [accessToken]);

  const brands = useMemo(
    () => Array.from(new Set(allItems.map(brandOf).filter(Boolean))).sort(),
    [allItems],
  );

  const tabCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of TABS) {
      counts[t.key] = t.cats === null
        ? allItems.length
        : allItems.filter((i) => t.cats!.includes((i.attributes?.category || '').toLowerCase())).length;
    }
    return counts;
  }, [allItems]);

  const filtered = useMemo(() => {
    const activeTab = TABS.find((t) => t.key === tab) || TABS[0];
    const q = search.trim().toLowerCase();
    const range = PRICE_RANGES.find((r) => r.value === priceRange) || PRICE_RANGES[0];
    let rows = allItems.filter((item) => {
      const cat = (item.attributes?.category || '').toLowerCase();
      if (activeTab.cats && !activeTab.cats.includes(cat)) return false;
      if (q && ![item.name, item.sku, brandOf(item)].some((v) => (v || '').toLowerCase().includes(q))) return false;
      if (brand && brandOf(item) !== brand) return false;
      if (item.price < range.min || item.price > range.max) return false;
      if (availability) {
        const a = (item.availability || 'in_stock').toLowerCase();
        const isBack = a.includes('back');
        if (availability === 'in_stock' && isBack) return false;
        if (availability === 'backorder' && !isBack) return false;
      }
      return true;
    });
    if (sort === 'price_low') rows = [...rows].sort((a, b) => a.price - b.price);
    else if (sort === 'price_high') rows = [...rows].sort((a, b) => b.price - a.price);
    else if (sort === 'availability') rows = [...rows].sort((a, b) => availabilityInfo(a).tone.localeCompare(availabilityInfo(b).tone));
    // Featured / discounted items are pinned to the top regardless of sort
    // (Array.prototype.sort is stable, so the in-group order is preserved).
    rows = [...rows].sort((a, b) => (b.attributes?.featured ? 1 : 0) - (a.attributes?.featured ? 1 : 0));
    return rows;
  }, [allItems, tab, search, brand, priceRange, availability, sort]);

  // Reset to first page whenever the result set changes.
  useEffect(() => { setPage(1); }, [tab, search, brand, priceRange, availability, sort]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  const pageNumbers = useMemo(() => {
    const nums: (number | '…')[] = [];
    const push = (n: number) => nums.push(n);
    if (pageCount <= 7) {
      for (let i = 1; i <= pageCount; i += 1) push(i);
    } else {
      push(1);
      if (safePage > 3) nums.push('…');
      for (let i = Math.max(2, safePage - 1); i <= Math.min(pageCount - 1, safePage + 1); i += 1) push(i);
      if (safePage < pageCount - 2) nums.push('…');
      push(pageCount);
    }
    return nums;
  }, [pageCount, safePage]);

  const handleQtyChange = async (lineId: string, itemId: string, newQty: number) => {
    setBusyItemId(itemId);
    try {
      if (newQty <= 0) await removeLine(lineId);
      else await updateLineQuantity(lineId, newQty);
    } finally {
      setBusyItemId(null);
    }
  };

  return (
    <section className="content-wrap fade-in cat2-page">
      <header className="cat2-header cat2-header-row">
        <div>
          <h1>Device catalog</h1>
          <p>Real SKUs from Meraki, Extreme, InHand &amp; T-Mobile. Add directly to your cart.</p>
        </div>
        <button className="cat2-viewcart" onClick={() => navigate('/shop/cart')}>
          <ShoppingCart size={17} /> View cart
        </button>
      </header>

      {error && <div className="error-text">{error}</div>}

      <div className="cat2-tabs">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button key={t.key} className={`cat2-tab ${tab === t.key ? 'active' : ''}`} onClick={() => setTab(t.key)}>
              <Icon size={16} /> {t.label} <span className="cat2-tab-count">{tabCounts[t.key] ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="cat2-bar">
        <div className="cat2-bar-search">
          <Search size={17} />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search model, brand, SKU…" />
        </div>
        <select value={brand} onChange={(e) => setBrand(e.target.value)}>
          <option value="">All brands</option>
          {brands.map((b) => <option key={b} value={b}>{b}</option>)}
        </select>
        <select value={priceRange} onChange={(e) => setPriceRange(e.target.value)}>
          {PRICE_RANGES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
        <select value={availability} onChange={(e) => setAvailability(e.target.value)}>
          <option value="">Any availability</option>
          <option value="in_stock">In stock</option>
          <option value="backorder">Backorder</option>
        </select>
        <select className="cat2-bar-sort" value={sort} onChange={(e) => setSort(e.target.value)}>
          {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      <div className="cat2-count-line">
        {filtered.length} products
        {filtered.length > 0 && <span className="cat2-count-page"> · page {safePage} of {pageCount}</span>}
      </div>

      {loading && <div className="cat2-note">Loading catalog…</div>}
      {!loading && filtered.length === 0 && <div className="cat2-note">No products matched your filters.</div>}

      <div className="cat2-grid">
        {pageItems.map((item, idx) => {
          const cat = item.attributes?.category || '';
          const viz = CATEGORY_ICON[cat] || { icon: Server, tone: 'blue' };
          const Icon = viz.icon;
          const stock = availabilityInfo(item);
          const tag = String(item.attributes?.badge || '') || (sort === 'recommended' && safePage === 1 && idx === 0 && tab === 'all' ? 'Recommended' : '');
          const papi = papiImageOf(item);
          const imageSrc = papi && !failedImg.has(item.id)
            ? getRouterImage({ id: item.id, sku: item.sku, name: item.name, brand: brandOf(item), model: String(item.attributes?.model || ''), imageUrl: papi })
            : '';
          const cartLine = cartLineMap.get(item.id);
          const isBusy = busyItemId === item.id;
          const isMultiline = !!item.attributes?.is_multiline;
          const perLine = Number(item.attributes?.per_line_price ?? item.price) || 0;
          const minLines = Number(item.attributes?.min_lines ?? 1) || 1;
          const maxLines = Number(item.attributes?.max_lines ?? 10) || 10;
          const lines = lineSel[item.id] ?? minLines;
          return (
            <article key={item.id} className="cat2-card">
              <Link to={`/shop/routers/${item.id}`} className={`cat2-viz tone-${viz.tone}`}>
                <span className={`cat2-stock ${stock.tone}`}>{stock.label}</span>
                {tag && <span className="cat2-tag">{tag}</span>}
                {imageSrc ? (
                  <img
                    className="cat2-img"
                    src={imageSrc}
                    alt={item.name}
                    loading="lazy"
                    onError={() => setFailedImg((prev) => new Set(prev).add(item.id))}
                  />
                ) : (
                  <span className="cat2-viz-icon"><Icon size={30} /></span>
                )}
              </Link>
              <div className="cat2-card-body">
                <p className="cat2-brand">{brandOf(item) || 'Catalog'}</p>
                <h3><Link to={`/shop/routers/${item.id}`}>{item.name}</Link></h3>
                <p className="cat2-sku">{item.sku}</p>
                {item.managed_service_price != null && (
                  <span className="cat2-managed"><ShieldCheck size={13} /> Managed from $ {item.managed_service_price.toFixed(0)} <small>/mo</small></span>
                )}
                {isMultiline && !cartLine && (
                  <label className="cat2-lines">
                    Lines
                    <select
                      value={lines}
                      onChange={(e) => setLineSel((s) => ({ ...s, [item.id]: Number(e.target.value) }))}
                    >
                      {Array.from({ length: maxLines - minLines + 1 }, (_, i) => minLines + i).map((n) => (
                        <option key={n} value={n}>{n}</option>
                      ))}
                    </select>
                  </label>
                )}
                <div className="cat2-card-foot">
                  <strong className="cat2-price">
                    ${(isMultiline ? perLine * lines : item.price).toFixed(2)}
                    {isMultiline && <small> /mo</small>}
                  </strong>
                  {cartLine ? (
                    <div className="qty-stepper">
                      <button className="qty-stepper-btn" disabled={isBusy}
                        onClick={() => cartLine.quantity <= 1 ? handleQtyChange(cartLine.lineId, item.id, 0) : handleQtyChange(cartLine.lineId, item.id, cartLine.quantity - 1)}>
                        {cartLine.quantity <= 1 ? <Trash2 size={13} /> : <Minus size={13} />}
                      </button>
                      <span className="qty-stepper-value">{cartLine.quantity}</span>
                      <button className="qty-stepper-btn" disabled={isBusy}
                        onClick={() => handleQtyChange(cartLine.lineId, item.id, cartLine.quantity + 1)}>
                        <Plus size={13} />
                      </button>
                    </div>
                  ) : (
                    <button className="cat2-add" disabled={isBusy} onClick={() => isMultiline ? addMultiline(item, lines) : openConfigurator(item)}>
                      <ShoppingCart size={15} /> Add
                    </button>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {configuring && (
        <BundleConfigurator
          product={configuring}
          onClose={() => setConfiguring(null)}
          onConfirm={async (selections, financialModel, interval) => {
            await addProductToCart(configuring.product_id ?? configuring.id, {
              selections, financialModel, interval, quantity: 1,
            });
          }}
        />
      )}

      {pageCount > 1 && (
        <nav className="cat2-pager" aria-label="Catalog pages">
          <button className="cat2-page-btn" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1}>
            <ChevronLeft size={15} /> Previous
          </button>
          <div className="cat2-page-nums">
            {pageNumbers.map((n, i) => (
              n === '…'
                ? <span key={`e${i}`} className="cat2-page-ellipsis">…</span>
                : <button key={n} className={`cat2-page-num-btn ${n === safePage ? 'active' : ''}`} onClick={() => setPage(n)}>{n}</button>
            ))}
          </div>
          <button className="cat2-page-btn" onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={safePage === pageCount}>
            Next <ChevronRight size={15} />
          </button>
        </nav>
      )}
    </section>
  );
};
