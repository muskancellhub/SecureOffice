import { ChevronRight, Layers2, ListTodo, ShoppingBasket, Workflow } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import * as commerceApi from '../api/commerceApi';
import { useAuth } from '../context/AuthContext';
import { useShop } from '../context/ShopContext';
import type { DesignXSuggestedLine } from '../types/commerce';

const steps = [
  { id: 1, title: 'Requirement', subtitle: 'Capture intent', icon: ListTodo },
  { id: 2, title: 'Build BOM', subtitle: 'AI/manual (auto-mixed)', icon: Layers2 },
  { id: 3, title: 'Review Cart', subtitle: 'Modify freely', icon: ShoppingBasket },
  { id: 4, title: 'Checkout', subtitle: 'Proposal + order', icon: Workflow },
] as const;

export const SolutionFlowPage = () => {
  const { accessToken, user } = useAuth();
  const { cart, refreshCart } = useShop();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const path = (searchParams.get('path') || 'ai').toLowerCase();
  const flowPath: 'ai' | 'manual' = path === 'manual' ? 'manual' : 'ai';

  const [activeStep, setActiveStep] = useState<number>(1);
  const [requirement, setRequirement] = useState('I need laptops and connectivity for 10 employees.');
  const [employeeCount, setEmployeeCount] = useState('10');
  const [siteCount, setSiteCount] = useState('1');
  const [designxSummary, setDesignxSummary] = useState('');
  const [designxSuggestions, setDesignxSuggestions] = useState<DesignXSuggestedLine[]>([]);
  const [unavailableCategories, setUnavailableCategories] = useState<string[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [actionError, setActionError] = useState('');
  const [actionNotice, setActionNotice] = useState('');

  const cartLineCount = cart?.lines?.length || 0;
  const standaloneServicesCount = useMemo(
    () => (cart?.lines || []).filter((line) => line.item_type === 'SERVICE' && !line.applies_to_line_id).length,
    [cart?.lines],
  );
  const onboardingCompleted = Boolean(user?.onboarding_completed);
  const pathLabel = flowPath === 'ai' ? 'AI Start' : 'Manual Start';
  const activeStepMeta = steps.find((step) => step.id === activeStep) || steps[0];
  const reviewLines = cart?.lines || [];

  useEffect(() => {
    if (!actionNotice) return;
    const timer = window.setTimeout(() => setActionNotice(''), 1800);
    return () => window.clearTimeout(timer);
  }, [actionNotice]);

  const onSuggestDesignX = async () => {
    if (!accessToken) return;
    setLoadingSuggestions(true);
    setActionError('');
    try {
      const response = await commerceApi.suggestDesignXBom(accessToken, {
        requirement,
        employee_count: Math.max(1, Number(employeeCount) || 1),
        site_count: Math.max(1, Number(siteCount) || 1),
        existing_customer: false,
      });
      setDesignxSummary(response.summary);
      setDesignxSuggestions(response.suggestions);
      setUnavailableCategories(response.unavailable_categories);
      setActiveStep(2);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to fetch DesignX BOM');
    } finally {
      setLoadingSuggestions(false);
    }
  };

  const addSuggestionToCart = async (line: DesignXSuggestedLine) => {
    if (!accessToken) return;
    setProcessing(true);
    setActionError('');
    setActionNotice('');
    try {
      await commerceApi.addCartLine(accessToken, {
        catalog_item_id: line.catalog_item_id,
        quantity: Math.max(1, line.quantity),
      });
      await refreshCart();
      setActionNotice('Added to cart');
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || `Failed to add ${line.name} to cart`);
    } finally {
      setProcessing(false);
    }
  };

  const addAllSuggestionsToCart = async () => {
    if (!accessToken || designxSuggestions.length === 0) return;
    setProcessing(true);
    setActionError('');
    setActionNotice('');
    try {
      for (const line of designxSuggestions) {
        await commerceApi.addCartLine(accessToken, {
          catalog_item_id: line.catalog_item_id,
          quantity: Math.max(1, line.quantity),
        });
      }
      await refreshCart();
      setActionNotice('Added to cart');
      setActiveStep(3);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to add suggestions to cart');
    } finally {
      setProcessing(false);
    }
  };

  const onGenerateProposal = async () => {
    if (!accessToken) return;
    if (!onboardingCompleted) {
      setActionError('Complete onboarding before checkout.');
      setActionNotice('');
      navigate('/shop/onboarding');
      return;
    }
    setProcessing(true);
    setActionError('');
    try {
      const quote = await commerceApi.generateQuote(accessToken);
      navigate(`/shop/quotes/${quote.id}`);
    } catch (err: any) {
      setActionError(err?.response?.data?.detail || 'Failed to create proposal from cart');
    } finally {
      setProcessing(false);
    }
  };

  const onStepSelect = (stepId: number) => {
    if (stepId === 4 && !onboardingCompleted) {
      setActionError('Complete onboarding before checkout.');
      setActionNotice('');
      navigate('/shop/onboarding');
      return;
    }
    setActionError('');
    setActiveStep(stepId);
  };

  const onNextStep = () => {
    if (activeStep === 3 && !onboardingCompleted) {
      setActionError('Complete onboarding before checkout.');
      setActionNotice('');
      navigate('/shop/onboarding');
      return;
    }
    setActionError('');
    setActiveStep((s) => Math.min(4, s + 1));
  };

  return (
    <section className="content-wrap fade-in solution-flow-page">
      <div className="solution-flow-hero row-between">
        <div className="solution-flow-hero-copy">
          <p className="solution-flow-eyebrow">Guided Procurement</p>
          <h1>{flowPath === 'ai' ? 'AI-Assisted Solution Builder' : 'Manual Solution Builder'}</h1>
          <p className="lead">
            {flowPath === 'ai' && 'Start with AI recommendations, then customize freely with catalog additions.'}
            {flowPath === 'manual' && 'Start manually from catalog and pull AI recommendations whenever needed.'}
          </p>
          <div className="solution-flow-hero-meta">
            <span className="flow-mode-chip">{pathLabel}</span>
            <span className="flow-assurance-chip">AI is optional. Catalog edits stay open end-to-end.</span>
          </div>
        </div>
        <div className="solution-flow-hero-side">
          <div className="solution-flow-progress-card">
            <span>Current stage</span>
            <strong>Step {activeStepMeta.id}: {activeStepMeta.title}</strong>
            <small>{activeStepMeta.subtitle}</small>
          </div>
          <button className="ghost-btn" type="button" onClick={() => navigate('/shop/flow-options')}>
            Back to path selection
          </button>
        </div>
      </div>

      <section className="dominos-stepper">
        {steps.map((step) => {
          const Icon = step.icon;
          const done = step.id < activeStep;
          const active = step.id === activeStep;
          return (
            <button key={step.id} type="button" className={`dominos-step ${active ? 'active' : ''} ${done ? 'done' : ''}`} onClick={() => onStepSelect(step.id)}>
              <span className="dominos-step-index">{step.id}</span>
              <span className="dominos-step-copy">
                <strong>{step.title}</strong>
                <small>{step.subtitle}</small>
              </span>
              <Icon size={15} />
            </button>
          );
        })}
      </section>

      {actionError && <div className="onboarding-alert error">{actionError}</div>}

      <section className="dominos-flow-layout">
        <article className="dominos-main-panel">
          {activeStep === 1 && (
            <div className="flow-stage-card">
              <div className="flow-stage-head">
                <h3>Step 1. What do you need?</h3>
                <span className="section-step">Input</span>
              </div>
              <label className="field-label">
                Requirement Brief
                <textarea
                  rows={6}
                  value={requirement}
                  onChange={(e) => setRequirement(e.target.value)}
                  placeholder="Describe what you need..."
                />
              </label>
              <div className="onboarding-input-grid">
                <label className="field-label">
                  Employees
                  <input type="number" value={employeeCount} onChange={(e) => setEmployeeCount(e.target.value)} placeholder="Employees" />
                </label>
                <label className="field-label">
                  Sites
                  <input type="number" value={siteCount} onChange={(e) => setSiteCount(e.target.value)} placeholder="Sites" />
                </label>
              </div>

              <button className="primary-btn" onClick={onSuggestDesignX} disabled={loadingSuggestions}>
                {loadingSuggestions ? 'Suggesting Products...' : 'Suggest Products'}
              </button>
              <div className="dashboard-link-row">
                <Link className="ghost-link" to="/shop/routers">Open full catalog</Link>
                <Link className="ghost-link" to="/shop/services">Open managed services</Link>
              </div>
            </div>
          )}

          {activeStep === 2 && (
            <div className="flow-stage-card">
              <div className="flow-stage-head">
                <h3>Step 2. Build BOM</h3>
                <span className="section-step">Review</span>
              </div>
              <p className="mini-note">{designxSummary || 'Run DesignX suggestion to generate a starting BOM.'}</p>
              {unavailableCategories.length > 0 && (
                <p className="mini-note">Unavailable categories: {unavailableCategories.join(', ')}</p>
              )}
              <div className="flow-suggestion-grid">
                {designxSuggestions.map((line) => (
                  <div key={`${line.catalog_item_id}-${line.name}`} className="flow-suggestion-card">
                    <div className="row-between">
                      <strong>{line.name}</strong>
                      <span className="badge">{line.type}</span>
                    </div>
                    <p>{line.reason}</p>
                    <p className="flow-suggestion-meta">Qty {line.quantity} · ${line.unit_price.toFixed(2)} · {line.billing_cycle}</p>
                    <button className="secondary-btn" onClick={() => addSuggestionToCart(line)} disabled={processing}>
                      Add to cart
                    </button>
                  </div>
                ))}
              </div>
              <div className="flow-action-row">
                {designxSuggestions.length > 0 && (
                  <button className="primary-btn" onClick={addAllSuggestionsToCart} disabled={processing}>
                    {processing ? 'Adding...' : 'Add All Suggestions'}
                  </button>
                )}
                <button className="secondary-btn" type="button" onClick={() => navigate('/shop/routers')}>
                  Explore Catalog (Modify)
                </button>
              </div>

              <div className="dashboard-link-row">
                <Link className="ghost-link" to="/shop/routers">Browse routers (CDW)</Link>
                <Link className="ghost-link" to="/shop/services">Browse managed services</Link>
                <Link className="ghost-link" to="/shop/cart">Open cart for edits</Link>
              </div>

              <p className="mini-note">
                AI suggestions are not final. You can remove, replace, and add catalog items before checkout.
              </p>
            </div>
          )}

          {activeStep === 3 && (
            <div className="flow-stage-card">
              <div className="flow-stage-head">
                <h3>Step 3. Review Cart</h3>
                <span className="section-step">Validate</span>
              </div>
              <div className="review-cart-list">
                {reviewLines.map((line) => (
                  <div key={line.id} className="review-cart-line">
                    <div>
                      <strong>{line.item_name}</strong>
                      <p className="mini-note">
                        {line.item_type}
                        {line.applies_to_item_name ? ` · Attached to ${line.applies_to_item_name}` : ''}
                      </p>
                    </div>
                    <div className="review-cart-line-meta">
                      <span>Qty {line.quantity}</span>
                      <strong>${line.line_total.toFixed(2)}</strong>
                    </div>
                  </div>
                ))}
                {reviewLines.length === 0 && <p className="mini-note">No items in cart yet.</p>}
              </div>
              <ul className="plain-bullets">
                <li>Total lines: {cartLineCount}</li>
                <li>Standalone managed services: {standaloneServicesCount}</li>
                <li>Projected 12-month total: ${(cart?.estimated_12_month_total || 0).toFixed(2)}</li>
              </ul>
              <div className="dashboard-link-row">
                <Link className="ghost-link" to="/shop/cart">Open full cart editor</Link>
                <Link className="ghost-link" to="/shop/routers">Add more catalog items</Link>
              </div>
            </div>
          )}

          {activeStep === 4 && (
            <div className="flow-stage-card">
              <div className="flow-stage-head">
                <h3>Step 4. Checkout</h3>
                <span className="section-step">Finalize</span>
              </div>
              <ul className="plain-bullets">
                <li>Create proposal from cart.</li>
                <li>Review BAFO quote and pricing controls.</li>
                <li>Validate payment method and convert quote to order.</li>
                <li>Category-based hardware/service fulfillment starts automatically.</li>
              </ul>
              <button className="primary-btn" onClick={onGenerateProposal} disabled={processing || cartLineCount === 0}>
                {processing ? 'Generating...' : 'Generate Proposal'}
              </button>
            </div>
          )}

          <div className="step-nav-row">
            <button className="ghost-btn" type="button" onClick={() => setActiveStep((s) => Math.max(1, s - 1))} disabled={activeStep === 1}>
              Previous
            </button>
            <button className="primary-btn" type="button" onClick={onNextStep} disabled={activeStep === 4}>
              Next Step <ChevronRight size={14} />
            </button>
          </div>
        </article>

        <aside className="dominos-summary-panel">
          <h3>Current Summary</h3>
          <p className="mini-note">Use this panel to track progress while you edit AI and catalog lines together.</p>
          <div className="summary-row">
            <span>Path</span>
            <strong>{flowPath.toUpperCase()}</strong>
          </div>
          <div className="summary-row">
            <span>Employees / Sites</span>
            <strong>{employeeCount} / {siteCount}</strong>
          </div>
          <div className="summary-row">
            <span>DesignX lines</span>
            <strong>{designxSuggestions.length}</strong>
          </div>
          <div className="summary-row">
            <span>Cart lines</span>
            <strong>{cartLineCount}</strong>
          </div>
          <div className="summary-row total">
            <span>Projected 12-month</span>
            <strong>${(cart?.estimated_12_month_total || 0).toFixed(2)}</strong>
          </div>
          <div className="dashboard-link-row">
            <Link className="ghost-link" to="/shop/cart">Open Cart</Link>
            <Link className="ghost-link" to="/shop/dashboard">Go to Dashboard</Link>
          </div>
        </aside>
      </section>
      {actionNotice && <div className="toast-notice">{actionNotice}</div>}
    </section>
  );
};
