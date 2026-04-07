import { useEffect, useState } from 'react';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import type { CatalogSyncResponse, IntegrationSyncLog } from '../types/commerce';

const SyncResultCard = ({ title, result }: { title: string; result: CatalogSyncResponse }) => (
  <div className="card">
    <h3>{title}</h3>
    <p>Created: {result.created_count} | Updated: {result.updated_count} | Synced: {result.synced_count}</p>
    {result.errors.length > 0 && (
      <details>
        <summary>Errors ({result.errors.length})</summary>
        <ul>{result.errors.map((e) => <li key={e}>{e}</li>)}</ul>
      </details>
    )}
  </div>
);

const LastSyncCard = ({ title, log }: { title: string; log: IntegrationSyncLog }) => (
  <div className="card">
    <h3>{title}</h3>
    <p>Status: <strong>{log.status}</strong></p>
    <p>Created: {log.created_count} | Updated: {log.updated_count} | Synced: {log.synced_count}</p>
    <p>Finished: {log.finished_at ? new Date(log.finished_at).toLocaleString() : 'n/a'}</p>
    {log.error_excerpt && (
      <details>
        <summary>Error/log excerpt</summary>
        <pre>{log.error_excerpt}</pre>
      </details>
    )}
  </div>
);

export const AdminCatalogSyncPage = () => {
  const { accessToken, user } = useAuth();
  const isAdmin = user?.role === 'SUPER_ADMIN' || user?.role === 'ADMIN';

  const [query, setQuery] = useState('business routers with sku, brand, model, ports, wifi standard, price and availability');
  const [limit, setLimit] = useState(20);
  const [cdwLoading, setCdwLoading] = useState(false);
  const [cdwError, setCdwError] = useState('');
  const [cdwResult, setCdwResult] = useState<CatalogSyncResponse | null>(null);
  const [cdwLastSync, setCdwLastSync] = useState<IntegrationSyncLog | null>(null);

  const [papiLoading, setPapiLoading] = useState(false);
  const [papiError, setPapiError] = useState('');
  const [papiResult, setPapiResult] = useState<CatalogSyncResponse | null>(null);
  const [papiLastSync, setPapiLastSync] = useState<IntegrationSyncLog | null>(null);
  const [papiPageSize, setPapiPageSize] = useState(100);
  const [papiMaxPages, setPapiMaxPages] = useState(20);

  const loadCdwLast = async () => {
    if (!accessToken) return;
    try { setCdwLastSync(await commerceApi.getCdwLastSync(accessToken)); } catch { setCdwLastSync(null); }
  };
  const loadPapiLast = async () => {
    if (!accessToken) return;
    try { setPapiLastSync(await commerceApi.getPapiLastSync(accessToken)); } catch { setPapiLastSync(null); }
  };

  useEffect(() => {
    if (isAdmin) { loadCdwLast(); loadPapiLast(); }
  }, [accessToken, isAdmin]);

  const runCdwSync = async () => {
    if (!accessToken) return;
    setCdwLoading(true);
    setCdwError('');
    try {
      setCdwResult(await commerceApi.syncCdwRouters(accessToken, query, limit));
      await loadCdwLast();
    } catch (err: any) {
      setCdwError(err?.response?.data?.detail || 'CDW sync failed');
    } finally {
      setCdwLoading(false);
    }
  };

  const runPapiSync = async () => {
    if (!accessToken) return;
    setPapiLoading(true);
    setPapiError('');
    try {
      setPapiResult(await commerceApi.syncPapiDevices(accessToken, { page_size: papiPageSize, max_pages: papiMaxPages }));
      await loadPapiLast();
    } catch (err: any) {
      setPapiError(err?.response?.data?.detail || 'T-Mobile Device Catalog sync failed');
    } finally {
      setPapiLoading(false);
    }
  };

  return (
    <section className="content-wrap fade-in">
      {!isAdmin && <div className="error-text">Admin access required.</div>}
      {isAdmin && (
        <>
          <div className="content-head">
            <h1>Admin - Catalog Sync</h1>
            <p className="lead">Sync devices from CDW and T-Mobile Device Catalog, and inspect latest run diagnostics.</p>
          </div>

          {/* CDW Section */}
          <h2 className="section-subhead">CDW Routers</h2>
          <div className="selector-card">
            <label>Query</label>
            <input value={query} onChange={(e) => setQuery(e.target.value)} />
            <label>Limit</label>
            <input type="number" value={limit} min={1} max={100} onChange={(e) => setLimit(Number(e.target.value) || 20)} />
            <button className="primary-btn" onClick={runCdwSync} disabled={cdwLoading}>
              {cdwLoading ? 'Syncing...' : 'Sync routers from CDW'}
            </button>
          </div>
          {cdwError && <div className="error-text">{cdwError}</div>}
          {cdwLastSync && <LastSyncCard title="CDW Last Sync" log={cdwLastSync} />}
          {cdwResult && <SyncResultCard title="CDW Current Run" result={cdwResult} />}

          {/* T-Mobile Device Catalog Section */}
          <h2 className="section-subhead">T-Mobile Device Catalog (Phones, Tablets, Hotspots)</h2>
          <div className="selector-card">
            <label>Page size</label>
            <input type="number" value={papiPageSize} min={1} max={100} onChange={(e) => setPapiPageSize(Number(e.target.value) || 100)} />
            <label>Max pages</label>
            <input type="number" value={papiMaxPages} min={1} max={50} onChange={(e) => setPapiMaxPages(Number(e.target.value) || 20)} />
            <button className="primary-btn" onClick={runPapiSync} disabled={papiLoading}>
              {papiLoading ? 'Syncing...' : 'Sync devices from T-Mobile'}
            </button>
          </div>
          {papiError && <div className="error-text">{papiError}</div>}
          {papiLastSync && <LastSyncCard title="T-Mobile Last Sync" log={papiLastSync} />}
          {papiResult && <SyncResultCard title="T-Mobile Current Run" result={papiResult} />}
        </>
      )}
    </section>
  );
};
