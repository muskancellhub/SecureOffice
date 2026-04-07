import { ArrowUpDown, Heart, Search, ShoppingCart, SlidersHorizontal } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { CatalogItem } from '../types/commerce';
import { getRouterImage } from '../utils/productImages';

const sortOptions = [
  { value: 'recommended', label: 'Recommended' },
  { value: 'price_low', label: 'Price low -> high' },
  { value: 'price_high', label: 'Price high -> low' },
  { value: 'availability', label: 'Availability' },
] as const;

const categoryOptions = [
  { value: '', label: 'All Devices' },
  { value: 'router', label: 'Routers (CDW)' },
  { value: 'laptop', label: 'Tablets & Laptops (T-Mobile Device Catalog)' },
  { value: 'phone', label: 'Phones (T-Mobile Device Catalog)' },
  { value: 'hotspot', label: 'Hotspots (T-Mobile Device Catalog)' },
] as const;

export const RoutersCatalogPage = () => {
  const { accessToken } = useAuth();
  const { addRouterToCart } = useShop();
  const [searchParams] = useSearchParams();
  const initialCategory = (['router', 'laptop', 'phone', 'hotspot'].includes(searchParams.get('category') || '') ? searchParams.get('category') : '') as '' | 'router' | 'laptop' | 'phone' | 'hotspot';
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [addedNotice, setAddedNotice] = useState('');
  const [page, setPage] = useState(1);

  const [category, setCategory] = useState<'' | 'router' | 'laptop' | 'phone' | 'hotspot'>(initialCategory);
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<'recommended' | 'price_low' | 'price_high' | 'availability'>('recommended');
  const [brand, setBrand] = useState('');
  const [availability, setAvailability] = useState('');
  const [minPrice, setMinPrice] = useState('');
  const [maxPrice, setMaxPrice] = useState('');

  const loadItems = async () => {
    if (!accessToken) return;
    setLoading(true);
    setError('');
    try {
      const filtered = await commerceApi.getCatalog(accessToken, {
        type: 'DEVICE',
        category: category || undefined,
        search: search || undefined,
        sort,
        brand: brand || undefined,
        availability: availability || undefined,
        min_price: minPrice ? Number(minPrice) : undefined,
        max_price: maxPrice ? Number(maxPrice) : undefined,
        page,
        page_size: 25,
      });
      setItems(filtered);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load catalog');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadItems();
  }, [accessToken, category, search, sort, brand, availability, minPrice, maxPrice, page]);

  useEffect(() => {
    setPage(1);
  }, [category, search, sort, brand, availability, minPrice, maxPrice]);

  const brands = useMemo(
    () => Array.from(new Set(items.map((row) => String(row.attributes?.brand || '').trim()).filter(Boolean))).sort(),
    [items],
  );

  const clearFilters = () => {
    setSearch('');
    setBrand('');
    setAvailability('');
    setMinPrice('');
    setMaxPrice('');
    setSort('recommended');
  };

  useEffect(() => {
    if (!addedNotice) return;
    const timer = window.setTimeout(() => setAddedNotice(''), 1400);
    return () => window.clearTimeout(timer);
  }, [addedNotice]);

  const title = useMemo(() => {
    if (!category) return 'Device Catalog';
    if (category === 'laptop') return 'Tablets & Laptops';
    if (category === 'phone') return 'Phones';
    if (category === 'hotspot') return 'Hotspots';
    return 'Routers';
  }, [category]);
  const hasNextPage = items.length === 25;

  return (
    <section className="content-wrap fade-in routers-catalog-page">
      <div className="content-head row-between">
        <div>
          <h1>{title}</h1>
          <p className="lead">Manual catalog exploration path. Add items directly to cart.</p>
        </div>
      </div>

      <div className="toolbar-grid routers-toolbar">
        <label className="search-wrap" aria-label="Search catalog">
          <Search size={17} />
          <input
            className="search-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by model, brand, SKU..."
          />
        </label>

        <label className="sort-wrap" aria-label="Sort catalog">
          <ArrowUpDown size={16} />
          <select value={sort} onChange={(e) => setSort(e.target.value as any)}>
            {sortOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error && <div className="error-text">{error}</div>}

      <div className="catalog-layout routers-layout">
        <aside className="filters-panel routers-filter-panel">
          <h4>
            <SlidersHorizontal size={16} />
            Filters
          </h4>

          <label>Category</label>
          <select value={category} onChange={(e) => setCategory(e.target.value as any)}>
            {categoryOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>

          <label>Brand</label>
          <select value={brand} onChange={(e) => setBrand(e.target.value)}>
            <option value="">All brands</option>
            {brands.map((entry) => (
              <option key={entry} value={entry}>{entry}</option>
            ))}
          </select>

          <label>Price range</label>
          <div className="inline-fields">
            <input type="number" value={minPrice} onChange={(e) => setMinPrice(e.target.value)} placeholder="Min" />
            <input type="number" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} placeholder="Max" />
          </div>

          <label>Availability</label>
          <select value={availability} onChange={(e) => setAvailability(e.target.value)}>
            <option value="">Any</option>
            <option value="in_stock">In stock</option>
            <option value="in stock">In stock (text)</option>
            <option value="backorder">Backorder</option>
          </select>

          <button className="ghost-btn clear-filter-btn" onClick={clearFilters}>
            Clear filters
          </button>
        </aside>

        <div className="products-zone">
          {loading && <div className="mini-note">Loading catalog...</div>}
          {!loading && items.length === 0 && <div className="mini-note">No products matched your filters.</div>}

          <div className="product-grid routers-grid">
            {items.map((item) => (
              <article key={item.id} className="router-card animated-card storefront-card">
                <div className="storefront-image-block">
                  <span className="badge stock-pill ok">{(item.availability || 'In stock').replace(/_/g, ' ')}</span>
                  <span className="wishlist-chip" aria-hidden="true">
                    <Heart size={12} />
                  </span>
                  <img
                    src={getRouterImage({
                      id: item.id,
                      sku: item.sku,
                      name: item.name,
                      brand: String(item.attributes?.brand || ''),
                      model: String(item.attributes?.model || ''),
                      imageUrl: String(item.attributes?.image_url || ''),
                    })}
                    alt={item.name}
                    className="product-image"
                    loading="lazy"
                  />
                </div>

                <div className="storefront-card-body">
                  <div className="item-meta-row">
                    <p className="brand-line">{String(item.attributes?.brand || item.vendor || 'Catalog')}</p>
                    <span className="item-availability-note">{(item.availability || 'In stock').replace(/_/g, ' ')}</span>
                  </div>

                  <h3>
                    <Link className="item-title-link" to={`/shop/routers/${item.id}`}>
                      {item.name}
                    </Link>
                  </h3>
                  <p className="storefront-subline">{String(item.attributes?.model || item.sku)}</p>

                  <div className="storefront-bottom-row">
                    <div className="storefront-price-col">
                      <strong className="storefront-price">${item.price.toFixed(2)}</strong>
                    </div>

                    <button
                      className="item-cart-btn"
                      aria-label="Add to cart"
                      onClick={async () => {
                        try {
                          await addRouterToCart(item.id, 1);
                          setAddedNotice('Added to cart');
                        } catch (err: any) {
                          setError(err?.response?.data?.detail || 'Failed to add item to cart');
                        }
                      }}
                    >
                      <ShoppingCart size={14} />
                      <span>Add to cart</span>
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <div className="dashboard-link-row">
            <button className="ghost-btn" onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page === 1 || loading}>
              Previous
            </button>
            <span className="mini-note">Page {page}</span>
            <button className="ghost-btn" onClick={() => setPage((prev) => prev + 1)} disabled={!hasNextPage || loading}>
              Next
            </button>
          </div>
        </div>
      </div>
      {addedNotice && <div className="toast-notice">{addedNotice}</div>}
    </section>
  );
};
