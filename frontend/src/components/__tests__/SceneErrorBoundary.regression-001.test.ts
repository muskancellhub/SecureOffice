// Regression: ISSUE-001 — public home page white-screened when WebGL context
// creation failed (headless browsers, software-rendered GPUs, sandboxed
// environments). The Three.js Canvas component throws synchronously and
// nothing was catching it, so the entire React tree unmounted.
// Found by /qa on 2026-05-01.
// Report: .gstack/qa-reports/qa-report-localhost-2026-05-01.md
//
// This test locks in the contract that SceneErrorBoundary:
//   1. Reports `hasError: true` from getDerivedStateFromError on any thrown error
//   2. Renders the fallback (not the children) once hasError is set
//   3. Renders children when hasError is false
//
// We avoid pulling in @testing-library/react (not installed) by exercising the
// class API directly — the same surface React itself uses.

import { describe, it, expect } from 'vitest';
import { SceneErrorBoundary } from '../SceneErrorBoundary';

describe('SceneErrorBoundary (regression: ISSUE-001)', () => {
  it('flips hasError true when getDerivedStateFromError sees any error', () => {
    const next = SceneErrorBoundary.getDerivedStateFromError();
    expect(next).toEqual({ hasError: true });
  });

  it('renders fallback when hasError is true', () => {
    const fallbackNode = 'webgl-fallback';
    const childNode = 'three-canvas';
    const instance = new SceneErrorBoundary({ fallback: fallbackNode, children: childNode });
    instance.state = { hasError: true };
    expect(instance.render()).toBe(fallbackNode);
  });

  it('renders children when hasError is false', () => {
    const fallbackNode = 'webgl-fallback';
    const childNode = 'three-canvas';
    const instance = new SceneErrorBoundary({ fallback: fallbackNode, children: childNode });
    instance.state = { hasError: false };
    expect(instance.render()).toBe(childNode);
  });
});
