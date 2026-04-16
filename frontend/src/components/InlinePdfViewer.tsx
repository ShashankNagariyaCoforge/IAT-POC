import { useState, useEffect, useRef } from 'react';
import { X, Maximize2, Download, ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).toString();

export interface BboxHighlight {
    page: number;
    bbox: [number, number, number, number]; // [x1, y1, x2, y2] in document units
    page_width: number;
    page_height: number;
    unit?: string;
}

interface Props {
    url: string;
    name?: string;
    onClose: () => void;
    onFullscreen?: () => void;
    /** When provided, switches to react-pdf mode with an interactive bbox overlay */
    highlight?: BboxHighlight | null;
}

/**
 * Inline PDF viewer with two modes:
 *   - No highlight → plain iframe (fast, full PDF)
 *   - highlight set → react-pdf single-page render + absolute bbox overlay div
 */
export function InlinePdfViewer({ url, name = 'Document', onClose, onFullscreen, highlight }: Props) {
    const [numPages, setNumPages] = useState<number>(0);
    const [currentPage, setCurrentPage] = useState<number>(highlight?.page ?? 1);
    const containerRef = useRef<HTMLDivElement>(null);
    const [containerWidth, setContainerWidth] = useState<number>(0);
    const [zoom, setZoom] = useState<number>(1.0);
    const [pdfLoadFailed, setPdfLoadFailed] = useState<boolean>(false);

    const ZOOM_STEP = 0.25;
    const ZOOM_MIN  = 0.5;
    const ZOOM_MAX  = 3.0;

    // Reset load failure state when URL changes
    useEffect(() => {
        setPdfLoadFailed(false);
    }, [url]);

    // Jump to the target page whenever highlight changes
    useEffect(() => {
        if (highlight?.page) setCurrentPage(highlight.page);
    }, [highlight]);

    // Measure container width so react-pdf scales to fill the panel
    useEffect(() => {
        if (!highlight) return;
        const el = containerRef.current;
        if (!el) return;
        const ro = new ResizeObserver(entries => {
            for (const entry of entries) setContainerWidth(entry.contentRect.width);
        });
        ro.observe(el);
        // Initial measurement
        setContainerWidth(el.clientWidth);
        return () => ro.disconnect();
    }, [highlight]);

    // Percentage-based overlay style — works at any zoom / container width
    const overlayStyle = (() => {
        if (!highlight?.bbox || !highlight.page_width || !highlight.page_height) return null;
        const [x1, y1, x2, y2] = highlight.bbox;
        return {
            position: 'absolute' as const,
            pointerEvents: 'none' as const,
            left:   `${(x1 / highlight.page_width)  * 100}%`,
            top:    `${(y1 / highlight.page_height) * 100}%`,
            width:  `${((x2 - x1) / highlight.page_width)  * 100}%`,
            height: `${((y2 - y1) / highlight.page_height) * 100}%`,
            border: '2px solid #6366f1',
            background: 'rgba(99, 102, 241, 0.18)',
            borderRadius: '3px',
            zIndex: 10,
        };
    })();

    return (
        <div style={{
            background: '#ffffff', borderRadius: '16px',
            border: '1px solid #e2e8f0', overflow: 'hidden',
            display: 'flex', flexDirection: 'column',
            height: '640px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.06)',
        }}>
            {/* Toolbar */}
            <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                padding: '8px 12px', borderBottom: '1px solid #f1f5f9',
                background: '#f8fafc', flexShrink: 0,
            }}>
                <svg viewBox="0 0 24 24" style={{ width: 14, height: 14, flexShrink: 0 }} fill="none" stroke="#ef4444" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                </svg>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {name}{highlight ? ` — page ${currentPage}` : ''}
                </span>

                {/* Page navigation — only in highlight (react-pdf) mode */}
                {highlight && numPages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <button onClick={() => setCurrentPage(p => Math.max(1, p - 1))} disabled={currentPage <= 1}
                            style={{ padding: '2px 4px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                            <ChevronLeft size={13} />
                        </button>
                        <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 600 }}>
                            {currentPage} / {numPages}
                        </span>
                        <button onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))} disabled={currentPage >= numPages}
                            style={{ padding: '2px 4px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                            <ChevronRight size={13} />
                        </button>
                    </div>
                )}

                {/* Zoom controls — shown in both modes */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                    <button
                        onClick={() => setZoom(z => Math.max(ZOOM_MIN, +(z - ZOOM_STEP).toFixed(2)))}
                        disabled={zoom <= ZOOM_MIN}
                        title="Zoom out"
                        style={{ padding: '3px', background: 'none', border: 'none', cursor: zoom <= ZOOM_MIN ? 'default' : 'pointer', color: zoom <= ZOOM_MIN ? '#cbd5e1' : '#64748b', display: 'flex', borderRadius: '4px' }}>
                        <ZoomOut size={13} />
                    </button>
                    <span style={{ fontSize: '10px', fontWeight: 700, color: '#64748b', minWidth: '32px', textAlign: 'center', userSelect: 'none' }}>
                        {Math.round(zoom * 100)}%
                    </span>
                    <button
                        onClick={() => setZoom(z => Math.min(ZOOM_MAX, +(z + ZOOM_STEP).toFixed(2)))}
                        disabled={zoom >= ZOOM_MAX}
                        title="Zoom in"
                        style={{ padding: '3px', background: 'none', border: 'none', cursor: zoom >= ZOOM_MAX ? 'default' : 'pointer', color: zoom >= ZOOM_MAX ? '#cbd5e1' : '#64748b', display: 'flex', borderRadius: '4px' }}>
                        <ZoomIn size={13} />
                    </button>
                </div>

                {onFullscreen && (
                    <button onClick={onFullscreen} title="Fullscreen"
                        style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                        <Maximize2 size={13} />
                    </button>
                )}
                <a href={url} download={name} target="_blank" rel="noopener noreferrer"
                    style={{ padding: '4px', borderRadius: '6px', color: '#94a3b8', display: 'flex', textDecoration: 'none' }}
                    title="Open / Download">
                    <Download size={13} />
                </a>
                <button onClick={onClose} title="Close"
                    style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                    <X size={14} />
                </button>
            </div>

            {/* Content */}
            <div ref={containerRef} style={{ flex: 1, overflow: 'auto', background: '#e2e8f0', position: 'relative' }}>
                {highlight && !pdfLoadFailed ? (
                    // react-pdf mode — single page with bbox overlay
                    <div style={{ display: 'flex', justifyContent: 'center', padding: '12px' }}>
                        <Document
                            file={url}
                            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
                            onLoadError={() => setPdfLoadFailed(true)}
                            loading={
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '300px', color: '#94a3b8', fontSize: 13 }}>
                                    Loading…
                                </div>
                            }
                        >
                            {/* position:relative gives % coordinates a reference frame */}
                            <div style={{ position: 'relative', display: 'inline-block' }}>
                                <Page
                                    pageNumber={currentPage}
                                    width={containerWidth > 24 ? (containerWidth - 24) * zoom : undefined}
                                    renderTextLayer={false}
                                    renderAnnotationLayer={false}
                                />
                                {/* Draw highlight only on the target page */}
                                {currentPage === highlight.page && overlayStyle && (
                                    <div style={overlayStyle} />
                                )}
                            </div>
                        </Document>
                    </div>
                ) : (
                    // iframe mode — full PDF browse
                    <iframe
                        src={`${url}#toolbar=0&navpanes=0&scrollbar=1`}
                        style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                        title={name}
                    />
                )}
            </div>
        </div>
    );
}
