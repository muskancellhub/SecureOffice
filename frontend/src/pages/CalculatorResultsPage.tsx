import { Link, Navigate } from 'react-router-dom';
import { NetworkCalculatorResult } from '../calculator';

const CALCULATOR_RESULT_STORAGE_KEY = 'secureOfficeNetworkEstimateV1';

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);

const formatNumber = (value: number): string => new Intl.NumberFormat('en-US').format(value);

export const CalculatorResultsPage = () => {
  const raw = localStorage.getItem(CALCULATOR_RESULT_STORAGE_KEY);
  if (!raw) return <Navigate to="/business-intake" replace />;

  let result: NetworkCalculatorResult;
  try {
    result = JSON.parse(raw) as NetworkCalculatorResult;
  } catch {
    return <Navigate to="/business-intake" replace />;
  }

  return (
    <div className="calculator-results-page">
      <div className="calculator-results-shell">
        <header className="calculator-results-header">
          <h1>Network Estimate (V1)</h1>
          <p>Planning estimate for SMB sizing. Final design may vary after detailed site validation.</p>
        </header>

        <section className="calculator-summary-grid">
          <article className="calculator-kpi-card">
            <span>Recommended Indoor APs</span>
            <strong>{formatNumber(result.summary.recommendedIndoorAPs)}</strong>
          </article>
          <article className="calculator-kpi-card">
            <span>Recommended Switches</span>
            <strong>{formatNumber(result.summary.recommendedSwitches)}</strong>
          </article>
          <article className="calculator-kpi-card">
            <span>Estimated CapEx</span>
            <strong>{formatCurrency(result.summary.estimatedCapEx)}</strong>
          </article>
        </section>

        <section className="calculator-details-grid">
          <article className="card calculator-detail-card">
            <h3>Counts</h3>
            <div className="calculator-row"><span>Coverage APs</span><strong>{result.counts.coverageAPs}</strong></div>
            <div className="calculator-row"><span>Capacity APs</span><strong>{result.counts.capacityAPs}</strong></div>
            <div className="calculator-row"><span>Indoor APs (max)</span><strong>{result.counts.indoorAPs}</strong></div>
            <div className="calculator-row"><span>Indoor APs Final</span><strong>{result.counts.indoorAPsFinal}</strong></div>
            <div className="calculator-row"><span>Switch Count</span><strong>{result.counts.switchCount}</strong></div>
          </article>

          <article className="card calculator-detail-card">
            <h3>RF Model</h3>
            <div className="calculator-row"><span>Allowed Path Loss (dB)</span><strong>{result.rfModel.allowedPathLossDb}</strong></div>
            <div className="calculator-row"><span>Estimated Radius (ft)</span><strong>{result.rfModel.estimatedRadiusFt}</strong></div>
            <div className="calculator-row"><span>Effective Cell Area (sqft)</span><strong>{formatNumber(result.rfModel.effectiveCellAreaSqft)}</strong></div>
          </article>

          <article className="card calculator-detail-card">
            <h3>Capacity Model</h3>
            <div className="calculator-row"><span>Effective Users</span><strong>{result.capacityModel.effectiveUsers}</strong></div>
            <div className="calculator-row"><span>Total Devices</span><strong>{result.capacityModel.totalDevices}</strong></div>
            <div className="calculator-row"><span>Usable Throughput / AP (Mbps)</span><strong>{result.capacityModel.usableThroughputMbps}</strong></div>
            <div className="calculator-row"><span>Required Throughput (Mbps)</span><strong>{result.capacityModel.requiredThroughputMbps}</strong></div>
          </article>

          <article className="card calculator-detail-card calculator-cost-card">
            <h3>Cost Breakdown</h3>
            <div className="calculator-row"><span>Indoor Hardware</span><strong>{formatCurrency(result.costs.indoorHardware)}</strong></div>
            <div className="calculator-row"><span>Licenses</span><strong>{formatCurrency(result.costs.licenses)}</strong></div>
            <div className="calculator-row"><span>Cabling</span><strong>{formatCurrency(result.costs.cabling)}</strong></div>
            <div className="calculator-row"><span>Labor</span><strong>{formatCurrency(result.costs.labor)}</strong></div>
            <div className="calculator-row"><span>Switch Cost</span><strong>{formatCurrency(result.costs.switchCost)}</strong></div>
            <div className="calculator-row"><span>UPS Cost</span><strong>{formatCurrency(result.costs.upsCost)}</strong></div>
            <div className="calculator-row"><span>CapEx Base</span><strong>{formatCurrency(result.costs.capExBase)}</strong></div>
            <div className="calculator-row"><span>CapEx + Markup</span><strong>{formatCurrency(result.costs.capExWithMarkup)}</strong></div>
            <div className="calculator-row total"><span>CapEx Final</span><strong>{formatCurrency(result.costs.capExFinal)}</strong></div>
          </article>
        </section>

        <div className="calculator-results-actions">
          <Link to="/business-intake" className="ghost-link">Edit Inputs</Link>
          <Link to="/login" className="primary-btn calculator-login-link">Continue to Login</Link>
        </div>
      </div>
    </div>
  );
};
