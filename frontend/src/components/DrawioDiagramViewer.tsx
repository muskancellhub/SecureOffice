import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

type DrawioDiagramViewerProps = {
  xml: string;
  title?: string;
  initialHeight?: number;
};

type DrawioEmbedMessage = {
  event?: string;
  [key: string]: unknown;
};

type DrawioEmbedFrameProps = {
  xml: string;
  title: string;
  height: number | string;
  className?: string;
};

const DRAWIO_EMBED_URL =
  'https://embed.diagrams.net/?embed=1&proto=json&spin=1&ui=min&libraries=1&saveAndExit=0&noSaveBtn=1&noExitBtn=1&modified=0';

const parseMessage = (raw: unknown): DrawioEmbedMessage | null => {
  if (!raw) return null;
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as DrawioEmbedMessage;
    } catch {
      return null;
    }
  }
  if (typeof raw === 'object') return raw as DrawioEmbedMessage;
  return null;
};

const DrawioEmbedFrame = ({ xml, title, height, className }: DrawioEmbedFrameProps) => {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [ready, setReady] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const postLoad = useCallback(() => {
    const target = iframeRef.current?.contentWindow;
    if (!target) return;
    target.postMessage(
      JSON.stringify({
        action: 'load',
        xml,
        title,
        autosave: 0,
        modified: '0',
      }),
      '*',
    );
  }, [xml, title]);

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) return;
      const message = parseMessage(event.data);
      if (!message) return;
      if (message.event === 'init') {
        setReady(true);
      } else if (message.event === 'load') {
        setLoaded(true);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  useEffect(() => {
    if (!ready || !xml) return;
    setLoaded(false);
    postLoad();
  }, [ready, xml, postLoad]);

  return (
    <div className="drawio-embed-shell">
      {!loaded && <p className="mini-note drawio-loading-note">Rendering diagram...</p>}
      <iframe
        ref={iframeRef}
        title={title}
        src={DRAWIO_EMBED_URL}
        className={className || 'drawio-viewer-frame'}
        style={{ height: typeof height === 'number' ? `${height}px` : height }}
      />
    </div>
  );
};

const effectiveInlineHeight = (initialHeight: number, expanded: boolean): number => {
  const base = Math.max(620, initialHeight);
  const desktopHeight = expanded ? Math.max(780, base + 120) : base;
  if (typeof window === 'undefined') return desktopHeight;
  if (window.innerWidth <= 760) return expanded ? 640 : 520;
  if (window.innerWidth <= 1024) return expanded ? 700 : 580;
  return desktopHeight;
};

export const DrawioDiagramViewer = ({ xml, title = 'SMB Network Diagram', initialHeight = 660 }: DrawioDiagramViewerProps) => {
  const [expanded, setExpanded] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  const inlineHeight = useMemo(() => effectiveInlineHeight(initialHeight, expanded), [initialHeight, expanded]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKeydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setFullscreen(false);
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeydown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeydown);
    };
  }, [fullscreen]);

  if (!xml?.trim()) {
    return <p className="mini-note">Diagram XML is not available yet.</p>;
  }

  return (
    <>
      <div className={`drawio-viewer-wrap ${expanded ? 'expanded' : ''}`}>
        <div className="row-between drawio-viewer-head">
          <strong>Diagram Preview</strong>
          <div className="drawio-viewer-actions">
            <button type="button" className="ghost-btn" onClick={() => setExpanded((prev) => !prev)}>
              {expanded ? 'Standard View' : 'Large View'}
            </button>
            <button type="button" className="ghost-btn" onClick={() => setFullscreen(true)}>
              Fullscreen
            </button>
          </div>
        </div>

        <DrawioEmbedFrame xml={xml} title={title} height={inlineHeight} />
      </div>

      {fullscreen && (
        <div className="drawio-modal-backdrop" role="dialog" aria-modal="true" onClick={() => setFullscreen(false)}>
          <div className="drawio-modal-panel" onClick={(event) => event.stopPropagation()}>
            <div className="row-between drawio-modal-head">
              <strong>{title}</strong>
              <button type="button" className="ghost-btn" onClick={() => setFullscreen(false)}>
                Close
              </button>
            </div>
            <DrawioEmbedFrame
              xml={xml}
              title={`${title} Fullscreen`}
              height="calc(100vh - 170px)"
              className="drawio-viewer-frame drawio-viewer-frame-modal"
            />
          </div>
        </div>
      )}
    </>
  );
};

