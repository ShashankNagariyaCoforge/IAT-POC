import { useRef, useState, useCallback } from 'react';
import { X, Maximize2, Download, ChevronLeft, ChevronRight } from 'lucide-react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

// Required: point pdfjs at its worker bundle
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url,
).toString();

export interface HighlightTarget {
    page: number;
    bbox: [number, number, number, number]; // [x1, y1, x2, y2] in ADI units
    page_width: number;
    page_height: number;
    coordinate_unit: string; // "inch" | "pixel"
}

interface Props {
    url: string;
    name?: string;
    onClose: () => void;
    onFullscreen?: () => void;
    // When provided: renders the specific page with highlight using react-pdf.
    // When absent:   renders the full document via a native iframe (browse mode).
    highlight?: HighlightTarget | null;
}

/**
 * Inline PDF viewer — two modes:
 *
 *  Browse mode  (no highlight): plain iframe, lets user scroll the whole PDF.
 *  Highlight mode (highlight set): react-pdf renders the specific page, SVG overlay
 *    draws a highlight rectangle around the extracted field.
 */
export function InlinePdfViewer({ url, name = 'Document', onClose, onFullscreen, highlight }: Props) {
    const containerRef = useRef<HTMLDivElement>(null);
    const [canvasSize, setCanvasSize] = useState<{ width: number; height: number } | null>(null);
    const [currentPage, setCurrentPage] = useState<number>(highlight?.page ?? 1);
    const [totalPages, setTotalPages] = useState<number>(0);

    // When highlight changes, jump to that page
    const targetPage = highlight ? highlight.page : currentPage;

    const handleDocumentLoad = useCallback(({ numPages }: { numPages: number }) => {
        setTotalPages(numPages);
        if (highlight) setCurrentPage(highlight.page);
    }, [highlight]);

    const handlePageRender = useCallback((page: any) => {
        setCanvasSize({ width: page.width, height: page.height });
    }, []);

    // Compute highlight rect as percentages of the rendered page
    const highlightStyle = (() => {
        if (!highlight?.bbox || !highlight.page_width || !highlight.page_height) return null;
        const [x1, y1, x2, y2] = highlight.bbox;
        return {
            left:   `${(x1 / highlight.page_width)  * 100}%`,
            top:    `${(y1 / highlight.page_height) * 100}%`,
            width:  `${((x2 - x1) / highlight.page_width)  * 100}%`,
            height: `${((y2 - y1) / highlight.page_height) * 100}%`,
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
                    {name}{highlight ? ` — page ${targetPage}${totalPages ? ` / ${totalPages}` : ''}` : ''}
                </span>

                {/* Page nav — only shown in highlight mode */}
                {highlight && totalPages > 1 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '2px' }}>
                        <button
                            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                            disabled={currentPage <= 1}
                            style={{ padding: '3px', borderRadius: '5px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex', opacity: currentPage <= 1 ? 0.4 : 1 }}
                        ><ChevronLeft size={13} /></button>
                        <button
                            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                            disabled={currentPage >= totalPages}
                            style={{ padding: '3px', borderRadius: '5px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex', opacity: currentPage >= totalPages ? 0.4 : 1 }}
                        ><ChevronRight size={13} /></button>
                    </div>
                )}

                {onFullscreen && (
                    <button onClick={onFullscreen} title="Fullscreen"
                        style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                        <Maximize2 size={13} />
                    </button>
                )}
                <a href={url} download={name} target="_blank" rel="noopener noreferrer"
                    style={{ padding: '4px', borderRadius: '6px', color: '#94a3b8', display: 'flex', textDecoration: 'none' }} title="Open / Download">
                    <Download size={13} />
                </a>
                <button onClick={onClose} title="Close"
                    style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}>
                    <X size={14} />
                </button>
            </div>

            {/* PDF content area */}
            <div style={{ flex: 1, overflow: 'auto', background: '#e2e8f0', display: 'flex', justifyContent: 'center' }}>
                {highlight ? (
                    /* ── Highlight mode: react-pdf + overlay ── */
                    <div ref={containerRef} style={{ position: 'relative', alignSelf: 'flex-start' }}>
                        <Document
                            file={url}
                            onLoadSuccess={handleDocumentLoad}
                            loading={
                                <div style={{ padding: '40px', color: '#94a3b8', fontSize: '13px' }}>Loading…</div>
                            }
                        >
                            <Page
                                pageNumber={currentPage}
                                onRenderSuccess={handlePageRender}
                                renderTextLayer={false}
                                renderAnnotationLayer={false}
                            />
                        </Document>

                        {/* Highlight overlay — shown only on the target page */}
                        {highlightStyle && currentPage === highlight.page && canvasSize && (
                            <div
                                style={{
                                    position: 'absolute',
                                    pointerEvents: 'none',
                                    border: '2px solid #6366f1',
                                    background: 'rgba(99, 102, 241, 0.18)',
                                    borderRadius: '3px',
                                    ...highlightStyle,
                                }}
                            />
                        )}
                    </div>
                ) : (
                    /* ── Browse mode: native iframe ── */
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
