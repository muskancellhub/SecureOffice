import { ArrowRight, Bot, Search, Workflow } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const FlowOptionsPage = () => {
  const navigate = useNavigate();

  return (
    <section className="content-wrap fade-in flow-options-page">
      <div className="flow-options-hero">
        <p className="flow-options-eyebrow">Start Procurement</p>
        <h1>Choose How You Want to Begin</h1>
        <p className="lead">
          Pick one of the two paths below. Both are fully flexible and can be mixed at any point before checkout.
        </p>
      </div>

      <div className="flow-options-grid">
        <button className="flow-option-card" onClick={() => navigate('/shop/solution-flow?path=ai')}>
          <div className="flow-card-head">
            <span className="option-icon"><Bot size={22} /></span>
            <span className="flow-card-kicker">Path 1</span>
          </div>
          <h3>AI / DesignX Suggested BOM</h3>
          <p className="flow-card-lead">
            Start with an AI-generated BOM from your requirement, then edit, replace, or add catalog items.
          </p>
          <div className="flow-card-meta">Best for: faster first draft</div>
          <span className="option-cta">Start AI Path <ArrowRight size={16} /></span>
        </button>

        <button className="flow-option-card" onClick={() => navigate('/shop/routers')}>
          <div className="flow-card-head">
            <span className="option-icon"><Search size={22} /></span>
            <span className="flow-card-kicker">Path 2</span>
          </div>
          <h3>Manual Catalog Exploration</h3>
          <p className="flow-card-lead">
            Browse all devices and services directly, then optionally pull AI suggestions later for refinement.
          </p>
          <div className="flow-card-meta">Best for: direct catalog control</div>
          <span className="option-cta">Open Catalog <ArrowRight size={16} /></span>
        </button>

        <button className="flow-option-card" onClick={() => navigate('/shop/designs/new')}>
          <div className="flow-card-head">
            <span className="option-icon"><Workflow size={22} /></span>
            <span className="flow-card-kicker">Path 3</span>
          </div>
          <h3>Calculator to BOM + Diagram</h3>
          <p className="flow-card-lead">
            Use your calculator snapshot to generate a network BOM, topology JSON, and draw.io XML, then submit with lead details.
          </p>
          <div className="flow-card-meta">Best for: stakeholder demo flow</div>
          <span className="option-cta">Start Design Flow <ArrowRight size={16} /></span>
        </button>
      </div>
    </section>
  );
};
