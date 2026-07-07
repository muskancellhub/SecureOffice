import { ArrowLeft, ArrowRight, Check, ShoppingCart, X } from 'lucide-react';
import { useState } from 'react';
import type { PlanSlide } from '../data/planInfo';

interface Props {
  planName: string;
  price?: string;
  unit?: string;
  slides: PlanSlide[];
  onClose: () => void;
  onGetStarted: () => void;
}

/** A simple carousel modal: walks through a plan's info slides (Next/Back),
 * ending in the "Get started" CTA. Self-contained styles (matches the
 * BundleConfigurator pattern). */
export default function PlanInfoModal({ planName, price, unit, slides, onClose, onGetStarted }: Props) {
  const [index, setIndex] = useState(0);
  const total = Math.max(1, slides.length);
  const slide = slides[index];
  const isLast = index >= total - 1;

  return (
    <div className="pim-overlay" role="dialog" aria-modal="true" aria-label={`${planName} details`} onClick={onClose}>
      <style>{`
        .pim-overlay { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.55); display: flex;
          align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
        .pim-modal { background: #fff; border-radius: 18px; width: 680px; max-width: 100%; max-height: 90vh;
          display: flex; flex-direction: column; box-shadow: 0 24px 64px rgba(0,0,0,0.28); overflow: hidden; }
        .pim-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
          padding: 22px 26px 14px; border-bottom: 1px solid #eef2f7; }
        .pim-head-titles { display: flex; flex-direction: column; gap: 4px; }
        .pim-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #473d7d; }
        .pim-plan { margin: 0; font-size: 19px; font-weight: 800; color: #131722; }
        .pim-price { font-size: 13px; color: #8a93a3; font-weight: 600; }
        .pim-close { background: transparent; border: 0; cursor: pointer; color: #8a93a3; padding: 4px; border-radius: 8px; }
        .pim-close:hover { background: #f1f3f7; color: #131722; }
        .pim-body { padding: 22px 26px; overflow-y: auto; flex: 1; }
        .pim-slide-title { margin: 0 0 6px; font-size: 22px; font-weight: 800; letter-spacing: -0.01em; color: #131722; }
        .pim-slide-sub { margin: 0 0 18px; font-size: 14.5px; line-height: 1.5; color: #5d6f89; }
        .pim-bullets { list-style: none; margin: 0; padding: 0; display: grid; gap: 11px; }
        .pim-bullets li { display: flex; align-items: flex-start; gap: 10px; font-size: 15px; line-height: 1.45; color: #2c3444; }
        .pim-bullets li svg { color: #18925a; flex-shrink: 0; margin-top: 2px; }
        .pim-sections { display: grid; grid-template-columns: 1fr 1fr; gap: 18px 24px; margin-top: 18px; }
        .pim-section h4 { margin: 0 0 8px; font-size: 13.5px; font-weight: 700; color: #473d7d; }
        .pim-section ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
        .pim-section li { font-size: 13.5px; color: #41506a; line-height: 1.4; padding-left: 14px; position: relative; }
        .pim-section li::before { content: '•'; position: absolute; left: 0; color: #473d7d; }
        .pim-table-wrap { overflow-x: auto; }
        .pim-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
        .pim-table th { text-align: left; padding: 8px 10px; border-bottom: 1px solid #e6eaf0; color: #8a93a3;
          font-weight: 600; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.02em; }
        .pim-table td { padding: 8px 10px; border-bottom: 1px solid #f1f4f8; color: #2c3444; }
        .pim-table td:first-child { font-weight: 600; color: #161b26; white-space: nowrap; }
        .pim-table tr:last-child td { border-bottom: 0; }
        .pim-foot { display: flex; align-items: center; gap: 14px; padding: 16px 26px 20px; border-top: 1px solid #eef2f7; }
        .pim-dots { display: flex; gap: 7px; margin-right: auto; }
        .pim-dot { width: 8px; height: 8px; border-radius: 999px; background: #dfe4ec; transition: background 140ms ease, width 140ms ease; }
        .pim-dot.on { width: 22px; background: #473d7d; }
        .pim-back { display: inline-flex; align-items: center; gap: 6px; height: 42px; padding: 0 16px; border: 1px solid #e4e8ef;
          border-radius: 11px; background: #fff; color: #3a4252; font-size: 14px; font-weight: 600; cursor: pointer; }
        .pim-back:disabled { opacity: 0.45; cursor: default; }
        .pim-next { display: inline-flex; align-items: center; gap: 8px; height: 42px; padding: 0 20px; border: 0; border-radius: 11px;
          background: #16181f; color: #fff; font-size: 14px; font-weight: 700; cursor: pointer; }
        .pim-next:hover { background: #2a2d36; }
        .pim-next.cta { background: #564a96; box-shadow: 0 10px 24px rgba(86, 74, 150, 0.3); }
        @media (max-width: 620px) { .pim-sections { grid-template-columns: 1fr; } }
      `}</style>
      <div className="pim-modal" onClick={(e) => e.stopPropagation()}>
        <div className="pim-head">
          <div className="pim-head-titles">
            <span className="pim-eyebrow">Plan details</span>
            <h2 className="pim-plan">{planName}</h2>
            {price && <span className="pim-price">{price} {unit}</span>}
          </div>
          <button className="pim-close" onClick={onClose} aria-label="Close"><X size={20} /></button>
        </div>

        <div className="pim-body">
          {slide && (
            <>
              <h3 className="pim-slide-title">{slide.title}</h3>
              {slide.subtitle && <p className="pim-slide-sub">{slide.subtitle}</p>}
              {slide.bullets && slide.bullets.length > 0 && (
                <ul className="pim-bullets">
                  {slide.bullets.map((b) => <li key={b}><Check size={16} /> {b}</li>)}
                </ul>
              )}
              {slide.table && (
                <div className="pim-table-wrap">
                  <table className="pim-table">
                    <thead>
                      <tr>{slide.table.columns.map((c) => <th key={c}>{c}</th>)}</tr>
                    </thead>
                    <tbody>
                      {slide.table.rows.map((row, ri) => (
                        <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {slide.sections && slide.sections.length > 0 && (
                <div className="pim-sections">
                  {slide.sections.map((sec) => (
                    <div key={sec.heading} className="pim-section">
                      <h4>{sec.heading}</h4>
                      <ul>{sec.items.map((it) => <li key={it}>{it}</li>)}</ul>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        <div className="pim-foot">
          <div className="pim-dots" aria-hidden="true">
            {slides.map((_, i) => <span key={i} className={`pim-dot${i === index ? ' on' : ''}`} />)}
          </div>
          <button className="pim-back" disabled={index === 0} onClick={() => setIndex((i) => Math.max(0, i - 1))}>
            <ArrowLeft size={15} /> Back
          </button>
          {isLast ? (
            <button className="pim-next cta" onClick={onGetStarted}>
              <ShoppingCart size={16} /> Get started
            </button>
          ) : (
            <button className="pim-next" onClick={() => setIndex((i) => Math.min(total - 1, i + 1))}>
              Next <ArrowRight size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
