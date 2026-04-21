import { useEffect, useState, useCallback, Fragment } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Cpu,
  ExternalLink,
  HardDrive,
  LayoutDashboard,
  MonitorCheck,
  RefreshCw,
  Server,
  Shield,
  Wifi,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import * as commerceApi from '../api/commerceApi';

/* ===================================================================
   Grafana embed config
   =================================================================== */

const GRAFANA_BASE_URL = (import.meta as any).env?.VITE_GRAFANA_URL || 'http://localhost:3000';

const GRAFANA_PANELS = [
  { title: 'Network Overview', uid: 'secureoffice-overview', panelId: undefined },
  { title: 'CPU Utilization', uid: 'secureoffice-overview', panelId: 6 },
  { title: 'Memory Utilization', uid: 'secureoffice-overview', panelId: 7 },
  { title: 'Network Traffic', uid: 'secureoffice-overview', panelId: 8 },
  { title: 'Disk Usage', uid: 'secureoffice-overview', panelId: 9 },
];

function grafanaEmbedUrl(uid: string, panelId?: number, from = 'now-1h', to = 'now'): string {
  if (panelId !== undefined) {
    return `${GRAFANA_BASE_URL}/d-solo/${uid}?orgId=1&panelId=${panelId}&from=${from}&to=${to}&theme=light`;
  }
  return `${GRAFANA_BASE_URL}/d/${uid}?orgId=1&from=${from}&to=${to}&theme=light&kiosk`;
}

type Tab = 'overview' | 'grafana';

/* ===================================================================
   Severity helpers
   =================================================================== */

const SEVERITY_META: Record<string, { label: string; cls: string }> = {
  disaster: { label: 'Disaster', cls: 'zabbix-sev-disaster' },
  high: { label: 'High', cls: 'zabbix-sev-high' },
  average: { label: 'Average', cls: 'zabbix-sev-average' },
  warning: { label: 'Warning', cls: 'zabbix-sev-warning' },
  information: { label: 'Info', cls: 'zabbix-sev-info' },
  not_classified: { label: 'N/C', cls: 'zabbix-sev-nc' },
};

const severityFromCode = (code: string | number): string => {
  const map: Record<string, string> = { '5': 'disaster', '4': 'high', '3': 'average', '2': 'warning', '1': 'information', '0': 'not_classified' };
  return map[String(code)] || 'not_classified';
};

function SeverityBadge({ level }: { level: string }) {
  const meta = SEVERITY_META[level] || SEVERITY_META.not_classified;
  return <span className={`zabbix-sev-badge ${meta.cls}`}>{meta.label}</span>;
}

/* ===================================================================
   Time helpers
   =================================================================== */

function timeAgo(unixStr: string): string {
  const seconds = Math.floor(Date.now() / 1000 - Number(unixStr));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function relativeAgo(minutes: number): string {
  return String(Math.floor(Date.now() / 1000 - minutes * 60));
}

/* ===================================================================
   Realistic demo data
   =================================================================== */

const DEMO_HOSTS = [
  { hostid: '10101', host: 'gw-core-01', name: 'Core Gateway (Cisco ISR 4431)', status: '0', interfaces: [{ ip: '10.0.0.1', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '2', name: 'Network Devices' }] },
  { hostid: '10102', host: 'sw-dist-01', name: 'Distribution Switch (Catalyst 9300)', status: '0', interfaces: [{ ip: '10.0.1.1', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '2', name: 'Network Devices' }] },
  { hostid: '10103', host: 'ap-floor1-01', name: 'Floor 1 Access Point (Meraki MR46)', status: '0', interfaces: [{ ip: '10.0.10.11', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '5', name: 'Wireless APs' }] },
  { hostid: '10104', host: 'ap-floor2-01', name: 'Floor 2 Access Point (Meraki MR46)', status: '0', interfaces: [{ ip: '10.0.10.12', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '5', name: 'Wireless APs' }] },
  { hostid: '10105', host: 'fw-edge-01', name: 'Edge Firewall (Fortinet 60F)', status: '0', interfaces: [{ ip: '10.0.0.254', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '3', name: 'Security Appliances' }] },
  { hostid: '10106', host: 'srv-app-01', name: 'Application Server (Ubuntu 22.04)', status: '0', interfaces: [{ ip: '10.0.2.10', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '4', name: 'Linux Servers' }] },
  { hostid: '10107', host: 'srv-db-01', name: 'Database Server (PostgreSQL)', status: '0', interfaces: [{ ip: '10.0.2.20', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '4', name: 'Linux Servers' }] },
  { hostid: '10108', host: 'cam-lobby-01', name: 'Lobby Camera (Axis M3065-V)', status: '1', interfaces: [{ ip: '10.0.20.5', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '6', name: 'IoT / Surveillance' }] },
  { hostid: '10109', host: 'pos-register-01', name: 'POS Terminal 1 (Windows IoT)', status: '0', interfaces: [{ ip: '10.0.30.1', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '7', name: 'POS Systems' }] },
  { hostid: '10110', host: 'ups-main-01', name: 'Main UPS (APC Smart-UPS 1500)', status: '0', interfaces: [{ ip: '10.0.0.200', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '8', name: 'Power / UPS' }] },
  { hostid: '10111', host: 'sw-access-01', name: 'Access Switch (Catalyst 9200L)', status: '0', interfaces: [{ ip: '10.0.1.10', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '2', name: 'Network Devices' }] },
  { hostid: '10112', host: 'printer-office', name: 'Office Printer (HP LaserJet)', status: '0', interfaces: [{ ip: '10.0.30.50', port: '10050', type: '1', main: '1' }], groups: [{ groupid: '9', name: 'Office Equipment' }] },
];

const now = () => relativeAgo(0);

const DEMO_PROBLEMS = [
  { eventid: '5001', objectid: '2001', name: 'Lobby Camera: ICMP ping timeout — host unreachable', severity: '4', acknowledged: '0', clock: relativeAgo(12), hosts: [{ hostid: '10108', name: 'Lobby Camera (Axis M3065-V)' }], tags: [] },
  { eventid: '5002', objectid: '2002', name: 'High CPU utilization (> 85% for 5m)', severity: '3', acknowledged: '1', clock: relativeAgo(47), hosts: [{ hostid: '10106', name: 'Application Server (Ubuntu 22.04)' }], tags: [] },
  { eventid: '5003', objectid: '2003', name: 'Disk space critically low (< 5% free on /data)', severity: '5', acknowledged: '0', clock: relativeAgo(3), hosts: [{ hostid: '10107', name: 'Database Server (PostgreSQL)' }], tags: [] },
  { eventid: '5004', objectid: '2004', name: 'UPS battery runtime below 15 minutes', severity: '4', acknowledged: '0', clock: relativeAgo(120), hosts: [{ hostid: '10110', name: 'Main UPS (APC Smart-UPS 1500)' }], tags: [] },
  { eventid: '5005', objectid: '2005', name: 'WiFi channel utilization > 70% on 5GHz band', severity: '2', acknowledged: '1', clock: relativeAgo(180), hosts: [{ hostid: '10103', name: 'Floor 1 Access Point (Meraki MR46)' }], tags: [] },
  { eventid: '5006', objectid: '2006', name: 'Interface GigabitEthernet0/1 link down', severity: '3', acknowledged: '0', clock: relativeAgo(8), hosts: [{ hostid: '10111', name: 'Access Switch (Catalyst 9200L)' }], tags: [] },
  { eventid: '5007', objectid: '2007', name: 'SSL certificate expires in 14 days', severity: '2', acknowledged: '0', clock: relativeAgo(1440), hosts: [{ hostid: '10105', name: 'Edge Firewall (Fortinet 60F)' }], tags: [] },
];

const DEMO_TRIGGERS = [
  { triggerid: '3001', description: 'ICMP ping timeout — host unreachable', priority: '4', status: '0', value: '1', lastchange: relativeAgo(12), hosts: [{ hostid: '10108', name: 'Lobby Camera (Axis M3065-V)' }] },
  { triggerid: '3002', description: '/data filesystem: disk space critically low', priority: '5', status: '0', value: '1', lastchange: relativeAgo(3), hosts: [{ hostid: '10107', name: 'Database Server (PostgreSQL)' }] },
  { triggerid: '3003', description: 'CPU utilization over 85% for 5 min', priority: '3', status: '0', value: '1', lastchange: relativeAgo(47), hosts: [{ hostid: '10106', name: 'Application Server (Ubuntu 22.04)' }] },
  { triggerid: '3004', description: 'UPS battery runtime critically low', priority: '4', status: '0', value: '1', lastchange: relativeAgo(120), hosts: [{ hostid: '10110', name: 'Main UPS (APC Smart-UPS 1500)' }] },
  { triggerid: '3005', description: 'GigabitEthernet0/1 link down', priority: '3', status: '0', value: '1', lastchange: relativeAgo(8), hosts: [{ hostid: '10111', name: 'Access Switch (Catalyst 9200L)' }] },
  { triggerid: '3006', description: '5GHz channel utilization high', priority: '2', status: '0', value: '1', lastchange: relativeAgo(180), hosts: [{ hostid: '10103', name: 'Floor 1 Access Point (Meraki MR46)' }] },
];

const DEMO_DASHBOARD = {
  total_hosts: DEMO_HOSTS.length,
  available_hosts: DEMO_HOSTS.filter((h) => h.status === '0').length,
  unavailable_hosts: DEMO_HOSTS.filter((h) => h.status !== '0').length,
  total_problems: DEMO_PROBLEMS.length,
  problems_by_severity: {
    disaster: 1,
    high: 2,
    average: 2,
    warning: 2,
    information: 0,
    not_classified: 0,
  },
  active_triggers: DEMO_TRIGGERS.length,
};

const DEMO_METRICS: Record<string, any[]> = {
  '10101': [
    { itemid: '1', name: 'CPU utilization', key_: 'system.cpu.util', lastvalue: '23.4', units: '%', lastclock: relativeAgo(1) },
    { itemid: '2', name: 'Memory utilization', key_: 'vm.memory.utilization', lastvalue: '61.2', units: '%', lastclock: relativeAgo(1) },
    { itemid: '3', name: 'Uptime', key_: 'system.uptime', lastvalue: '4821600', units: 'uptime', lastclock: relativeAgo(1) },
    { itemid: '4', name: 'ICMP ping', key_: 'icmpping', lastvalue: '1', units: '', lastclock: relativeAgo(0) },
  ],
  '10106': [
    { itemid: '10', name: 'CPU utilization', key_: 'system.cpu.util', lastvalue: '87.6', units: '%', lastclock: relativeAgo(1) },
    { itemid: '11', name: 'Memory utilization', key_: 'vm.memory.utilization', lastvalue: '72.1', units: '%', lastclock: relativeAgo(1) },
    { itemid: '12', name: 'Disk / used', key_: 'vfs.fs.size[/,pused]', lastvalue: '54.3', units: '%', lastclock: relativeAgo(2) },
    { itemid: '13', name: 'Disk /data used', key_: 'vfs.fs.size[/data,pused]', lastvalue: '68.7', units: '%', lastclock: relativeAgo(2) },
    { itemid: '14', name: 'Network in (eth0)', key_: 'net.if.in[eth0]', lastvalue: '245820416', units: 'Bps', lastclock: relativeAgo(1) },
    { itemid: '15', name: 'Uptime', key_: 'system.uptime', lastvalue: '2592000', units: 'uptime', lastclock: relativeAgo(1) },
  ],
  '10107': [
    { itemid: '20', name: 'CPU utilization', key_: 'system.cpu.util', lastvalue: '42.1', units: '%', lastclock: relativeAgo(1) },
    { itemid: '21', name: 'Memory utilization', key_: 'vm.memory.utilization', lastvalue: '83.9', units: '%', lastclock: relativeAgo(1) },
    { itemid: '22', name: 'Disk /data used', key_: 'vfs.fs.size[/data,pused]', lastvalue: '96.2', units: '%', lastclock: relativeAgo(1) },
    { itemid: '23', name: 'Disk / used', key_: 'vfs.fs.size[/,pused]', lastvalue: '47.5', units: '%', lastclock: relativeAgo(2) },
    { itemid: '24', name: 'PostgreSQL connections', key_: 'net.if.in[eth0]', lastvalue: '142', units: '', lastclock: relativeAgo(1) },
  ],
  '10105': [
    { itemid: '30', name: 'CPU utilization', key_: 'system.cpu.util', lastvalue: '15.8', units: '%', lastclock: relativeAgo(1) },
    { itemid: '31', name: 'Memory utilization', key_: 'vm.memory.utilization', lastvalue: '44.2', units: '%', lastclock: relativeAgo(1) },
    { itemid: '32', name: 'Active sessions', key_: 'net.if.in[wan1]', lastvalue: '328', units: '', lastclock: relativeAgo(1) },
    { itemid: '33', name: 'Throughput in (wan1)', key_: 'net.if.in[wan1,bps]', lastvalue: '52428800', units: 'Bps', lastclock: relativeAgo(1) },
    { itemid: '34', name: 'ICMP ping', key_: 'icmpping', lastvalue: '1', units: '', lastclock: relativeAgo(0) },
  ],
};

// Default metric set for hosts without specific data
const DEFAULT_METRICS = [
  { itemid: '90', name: 'ICMP ping', key_: 'icmpping', lastvalue: '1', units: '', lastclock: relativeAgo(0) },
  { itemid: '91', name: 'Agent ping', key_: 'agent.ping', lastvalue: '1', units: '', lastclock: relativeAgo(0) },
  { itemid: '92', name: 'Uptime', key_: 'system.uptime', lastvalue: '1209600', units: 'uptime', lastclock: relativeAgo(1) },
];

function formatMetricValue(m: any): string {
  if (m.units === 'uptime') {
    const secs = Number(m.lastvalue);
    const days = Math.floor(secs / 86400);
    return `${days}d`;
  }
  if (m.units === 'Bps') {
    const mbps = Number(m.lastvalue) / 1_000_000;
    return `${mbps.toFixed(1)} Mbps`;
  }
  return `${m.lastvalue}${m.units ? ' ' + m.units : ''}`;
}

/* ===================================================================
   Main Component
   =================================================================== */

export const ZabbixPage = () => {
  const { accessToken } = useAuth();
  const [dashboard, setDashboard] = useState<any>(null);
  const [hosts, setHosts] = useState<any[]>([]);
  const [problems, setProblems] = useState<any[]>([]);
  const [triggers, setTriggers] = useState<any[]>([]);
  const [expandedHost, setExpandedHost] = useState<string | null>(null);
  const [hostMetrics, setHostMetrics] = useState<any[]>([]);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isDemo, setIsDemo] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [grafanaTimeRange, setGrafanaTimeRange] = useState('now-1h');

  const loadDemoData = useCallback(() => {
    setDashboard(DEMO_DASHBOARD);
    setHosts(DEMO_HOSTS);
    setProblems(DEMO_PROBLEMS);
    setTriggers(DEMO_TRIGGERS);
    setIsDemo(true);
    setLastRefresh(new Date());
    setLoading(false);
  }, []);

  const fetchAll = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [dash, h, p, t] = await Promise.all([
        commerceApi.fetchZabbixDashboard(accessToken),
        commerceApi.fetchZabbixHosts(accessToken),
        commerceApi.fetchZabbixProblems(accessToken),
        commerceApi.fetchZabbixTriggers(accessToken),
      ]);
      setDashboard(dash);
      setHosts(h);
      setProblems(p);
      setTriggers(t);
      setIsDemo(false);
      setLastRefresh(new Date());
    } catch {
      // API unavailable — fall back to demo data
      loadDemoData();
    } finally {
      setLoading(false);
    }
  }, [accessToken, loadDemoData]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const onExpandHost = async (hostId: string) => {
    if (expandedHost === hostId) {
      setExpandedHost(null);
      return;
    }
    setExpandedHost(hostId);
    setHostMetrics([]);
    setMetricsLoading(true);

    if (isDemo) {
      // Simulate a short loading delay
      await new Promise((r) => setTimeout(r, 300));
      setHostMetrics(DEMO_METRICS[hostId] || DEFAULT_METRICS);
      setMetricsLoading(false);
      return;
    }

    try {
      const m = await commerceApi.fetchZabbixHostMetrics(accessToken!, hostId);
      setHostMetrics(m);
    } catch {
      setHostMetrics([]);
    } finally {
      setMetricsLoading(false);
    }
  };

  /* ---------- render ---------- */

  return (
    <section className="content-wrap zabbix-page">
      {/* header */}
      <div className="content-head">
        <h1><MonitorCheck size={20} /> Zabbix Monitoring</h1>
        <div className="zabbix-header-actions">
          {isDemo && activeTab === 'overview' && <span className="zabbix-demo-badge">Demo Data</span>}
          {lastRefresh && activeTab === 'overview' && (
            <span className="zabbix-last-refresh">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          {activeTab === 'overview' && (
            <button className="ghost-btn" onClick={fetchAll} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'spin-icon' : ''} /> Refresh
            </button>
          )}
          {activeTab === 'grafana' && (
            <a
              href={`${GRAFANA_BASE_URL}/d/secureoffice-overview`}
              target="_blank"
              rel="noopener noreferrer"
              className="ghost-btn"
            >
              Open Grafana <ExternalLink size={13} />
            </a>
          )}
        </div>
      </div>

      {/* tabs */}
      <div className="zabbix-tabs">
        <button
          className={`zabbix-tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          <LayoutDashboard size={14} /> Overview
        </button>
        <button
          className={`zabbix-tab ${activeTab === 'grafana' ? 'active' : ''}`}
          onClick={() => setActiveTab('grafana')}
        >
          <BarChart3 size={14} /> Grafana Dashboards
        </button>
      </div>

      {/* ========== Grafana Tab ========== */}
      {activeTab === 'grafana' && (
        <div className="zabbix-grafana-section">
          <div className="zabbix-grafana-controls">
            <span className="zabbix-grafana-label">Time range:</span>
            <select
              value={grafanaTimeRange}
              onChange={(e) => setGrafanaTimeRange(e.target.value)}
              className="zabbix-grafana-select"
            >
              <option value="now-15m">Last 15 min</option>
              <option value="now-1h">Last 1 hour</option>
              <option value="now-3h">Last 3 hours</option>
              <option value="now-6h">Last 6 hours</option>
              <option value="now-12h">Last 12 hours</option>
              <option value="now-24h">Last 24 hours</option>
              <option value="now-7d">Last 7 days</option>
            </select>
          </div>

          {/* Full dashboard embed */}
          <div className="zabbix-grafana-full">
            <iframe
              src={grafanaEmbedUrl('secureoffice-overview', undefined, grafanaTimeRange)}
              title="Secure AI Office Network Overview"
              className="zabbix-grafana-iframe-full"
            />
          </div>

          {/* Individual panels */}
          <div className="zabbix-grafana-grid">
            {GRAFANA_PANELS.filter((p) => p.panelId !== undefined).map((panel) => (
              <div key={panel.panelId} className="zabbix-grafana-card">
                <h3>{panel.title}</h3>
                <iframe
                  src={grafanaEmbedUrl(panel.uid, panel.panelId, grafanaTimeRange)}
                  title={panel.title}
                  className="zabbix-grafana-iframe"
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ========== Overview Tab ========== */}
      {activeTab === 'overview' && <>

      {/* ---- hero KPI row ---- */}
      {dashboard && (
        <div className="zbx-hero-row">
          <div className="zbx-hero-card zbx-hero-total">
            <div className="zbx-hero-icon"><Server size={22} /></div>
            <div className="zbx-hero-info">
              <span className="zbx-hero-num">{dashboard.total_hosts}</span>
              <span className="zbx-hero-label">Total Hosts</span>
            </div>
            <div className="zbx-hero-ring">
              <svg viewBox="0 0 36 36">
                <path className="zbx-ring-bg" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
                <path className="zbx-ring-fill zbx-ring-green" strokeDasharray={`${dashboard.total_hosts > 0 ? (dashboard.available_hosts / dashboard.total_hosts) * 100 : 0}, 100`} d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
              </svg>
              <span className="zbx-ring-pct">{dashboard.total_hosts > 0 ? Math.round((dashboard.available_hosts / dashboard.total_hosts) * 100) : 0}%</span>
            </div>
          </div>
          <div className="zbx-hero-card zbx-hero-ok">
            <div className="zbx-hero-icon"><CheckCircle2 size={22} /></div>
            <div className="zbx-hero-info">
              <span className="zbx-hero-num">{dashboard.available_hosts}</span>
              <span className="zbx-hero-label">Available</span>
            </div>
          </div>
          <div className="zbx-hero-card zbx-hero-down">
            <div className="zbx-hero-icon"><AlertTriangle size={22} /></div>
            <div className="zbx-hero-info">
              <span className="zbx-hero-num">{dashboard.unavailable_hosts}</span>
              <span className="zbx-hero-label">Unavailable</span>
            </div>
          </div>
          <div className="zbx-hero-card zbx-hero-problems">
            <div className="zbx-hero-icon"><Shield size={22} /></div>
            <div className="zbx-hero-info">
              <span className="zbx-hero-num">{dashboard.total_problems}</span>
              <span className="zbx-hero-label">Problems</span>
            </div>
          </div>
          <div className="zbx-hero-card zbx-hero-triggers">
            <div className="zbx-hero-icon"><Activity size={22} /></div>
            <div className="zbx-hero-info">
              <span className="zbx-hero-num">{dashboard.active_triggers}</span>
              <span className="zbx-hero-label">Triggers</span>
            </div>
          </div>
        </div>
      )}

      {/* ---- severity bar ---- */}
      {dashboard?.problems_by_severity && (
        <div className="zbx-severity-bar">
          {Object.entries(dashboard.problems_by_severity)
            .filter(([, count]) => (count as number) > 0)
            .map(([sev, count]) => {
              const meta = SEVERITY_META[sev] || SEVERITY_META.not_classified;
              return (
                <div key={sev} className={`zbx-sev-pill ${meta.cls}`}>
                  <strong>{count as number}</strong>
                  <span>{meta.label}</span>
                </div>
              );
            })}
          {Object.values(dashboard.problems_by_severity).every((c) => c === 0) && (
            <div className="zbx-sev-pill zbx-sev-clear"><CheckCircle2 size={13} /> All clear</div>
          )}
        </div>
      )}

      {/* ---- two-column layout: hosts + problems ---- */}
      <div className="zbx-twin-grid">
        {/* hosts */}
        <div className="zbx-panel">
          <div className="zbx-panel-head">
            <h2><Server size={15} /> Hosts</h2>
            <span className="zbx-panel-count">{hosts.length}</span>
          </div>
          {hosts.length === 0 && !loading ? (
            <p className="zabbix-empty">No monitored hosts found.</p>
          ) : (
            <div className="zbx-host-list">
              {hosts.map((h: any) => {
                const ip = h.interfaces?.[0]?.ip || '-';
                const isUp = String(h.status) === '0';
                const expanded = expandedHost === h.hostid;
                const groups = (h.hostgroups || h.groups || []).map((g: any) => g.name).join(', ');
                return (
                  <Fragment key={h.hostid}>
                    <div className={`zbx-host-item ${expanded ? 'expanded' : ''}`} onClick={() => onExpandHost(h.hostid)}>
                      <span className={`zbx-dot ${isUp ? 'up' : 'down'}`} />
                      <div className="zbx-host-main">
                        <span className="zbx-host-name">{h.name || h.host}</span>
                        <span className="zbx-host-meta">{ip} {groups ? `· ${groups}` : ''}</span>
                      </div>
                      <span className={`zbx-host-status ${isUp ? 'up' : 'down'}`}>{isUp ? 'Up' : 'Down'}</span>
                      {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </div>
                    {expanded && (
                      <div className="zbx-host-expand">
                        {metricsLoading ? (
                          <p className="zabbix-empty">Loading metrics...</p>
                        ) : hostMetrics.length === 0 ? (
                          <p className="zabbix-empty">No metrics available.</p>
                        ) : (
                          <div className="zbx-mini-metrics">
                            {hostMetrics.map((m: any) => (
                              <div key={m.itemid} className="zbx-mini-metric">
                                <span className="zbx-mm-name">{m.name}</span>
                                <span className="zbx-mm-val">{formatMetricValue(m)}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </Fragment>
                );
              })}
            </div>
          )}
        </div>

        {/* problems */}
        <div className="zbx-panel">
          <div className="zbx-panel-head">
            <h2><AlertTriangle size={15} /> Active Problems</h2>
            <span className="zbx-panel-count">{problems.length}</span>
          </div>
          {problems.length === 0 && !loading ? (
            <div className="zabbix-all-clear">
              <CheckCircle2 size={28} />
              <span>No active problems</span>
            </div>
          ) : (
            <div className="zbx-problem-list">
              {problems.map((p: any) => {
                const sev = severityFromCode(p.severity);
                const hostName = p.hosts?.[0]?.name || '-';
                const meta = SEVERITY_META[sev] || SEVERITY_META.not_classified;
                return (
                  <div key={p.eventid} className={`zbx-problem-item ${meta.cls}`}>
                    <div className="zbx-problem-sev"><SeverityBadge level={sev} /></div>
                    <div className="zbx-problem-body">
                      <span className="zbx-problem-name">{p.name}</span>
                      <span className="zbx-problem-meta">
                        {hostName} · {timeAgo(p.clock)}
                        {p.acknowledged === '1' && <> · <CheckCircle2 size={12} className="zabbix-ack-yes" /> Ack</>}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ---- triggers ---- */}
      <div className="zbx-panel">
        <div className="zbx-panel-head">
          <h2><HardDrive size={15} /> Active Triggers</h2>
          <span className="zbx-panel-count">{triggers.length}</span>
        </div>
        {triggers.length === 0 && !loading ? (
          <p className="zabbix-empty">No active triggers.</p>
        ) : (
          <div className="zbx-trigger-grid">
            {triggers.map((t: any) => {
              const sev = severityFromCode(t.priority);
              const hostName = t.hosts?.[0]?.name || '-';
              return (
                <div key={t.triggerid} className="zbx-trigger-card">
                  <SeverityBadge level={sev} />
                  <div className="zbx-trigger-body">
                    <span className="zbx-trigger-desc">{t.description}</span>
                    <span className="zbx-trigger-meta">{hostName} · {t.lastchange ? timeAgo(t.lastchange) : '-'}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
      </>}
    </section>
  );
};
