import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  fallback: ReactNode;
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Catches synchronous render errors from a child subtree (notably the
 * react-three-fiber Canvas, which throws when WebGL context creation fails
 * in headless / software-rendered / GPU-disabled environments) and renders
 * the provided fallback instead of letting the whole app white-screen.
 *
 * Suspense alone is not enough here: it only handles async loading, not
 * thrown errors from the WebGL renderer.
 */
export class SceneErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (import.meta.env.DEV) {
      console.warn('[SceneErrorBoundary] caught:', error.message, info.componentStack);
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

export default SceneErrorBoundary;
