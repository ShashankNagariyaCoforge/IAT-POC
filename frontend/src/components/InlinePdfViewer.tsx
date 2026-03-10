import { X, Maximize2, Download } from 'lucide-react';

interface Props {
    url: string;
    name?: string;
    onClose: () => void;
    onFullscreen?: () => void;
}

/**
 * Inline PDF viewer — slides in to replace the left column panel.
 * Uses a native iframe for simplicity. For zoom/page control, onFullscreen opens PdfViewerModal.
 */
export function InlinePdfViewer({ url, name = 'Document', onClose, onFullscreen }: Props) {
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
                    {name}
                </span>
                {onFullscreen && (
                    <button
                        onClick={onFullscreen}
                        title="Fullscreen"
                        style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
                    >
                        <Maximize2 size={13} />
                    </button>
                )}
                <a
                    href={url}
                    download={name}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ padding: '4px', borderRadius: '6px', color: '#94a3b8', display: 'flex', textDecoration: 'none' }}
                    title="Open / Download"
                >
                    <Download size={13} />
                </a>
                <button
                    onClick={onClose}
                    title="Close"
                    style={{ padding: '4px', borderRadius: '6px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
                >
                    <X size={14} />
                </button>
            </div>

            {/* PDF iframe */}
            <div style={{ flex: 1, overflow: 'hidden', background: '#e2e8f0' }}>
                <iframe
                    src={`${url}#toolbar=0&navpanes=0&scrollbar=1`}
                    style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                    title={name}
                />
            </div>
        </div>
    );
}
