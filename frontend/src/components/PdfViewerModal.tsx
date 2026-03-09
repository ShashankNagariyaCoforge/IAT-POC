import { useEffect, useRef } from 'react';
import { X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut, Download, Loader2, AlertTriangle } from 'lucide-react';

interface Props {
    url: string;
    name?: string;
    onClose: () => void;
}

export function PdfViewerModal({ url, name = 'Document', onClose }: Props) {
    const iframeRef = useRef<HTMLIFrameElement>(null);

    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [onClose]);

    return (
        <div
            style={{
                position: 'fixed', inset: 0, zIndex: 1000,
                background: 'rgba(15,23,42,0.85)', backdropFilter: 'blur(8px)',
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
            }}
            onClick={e => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div style={{
                background: '#ffffff', borderRadius: '20px',
                display: 'flex', flexDirection: 'column',
                width: '100%', maxWidth: '960px', height: '90vh',
                overflow: 'hidden', boxShadow: '0 40px 80px rgba(0,0,0,0.4)',
            }}>
                {/* Header */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '10px',
                    padding: '12px 16px',
                    background: '#0f172a', borderRadius: '20px 20px 0 0',
                    flexShrink: 0,
                }}>
                    <svg viewBox="0 0 24 24" style={{ width: 18, height: 18, flexShrink: 0 }} fill="none" stroke="#ef4444" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                    </svg>
                    <span style={{ color: '#ffffff', fontWeight: 700, fontSize: '13px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {name}
                    </span>
                    <a
                        href={url}
                        download={name}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ padding: '6px', borderRadius: '8px', color: '#94a3b8', display: 'flex', textDecoration: 'none' }}
                        title="Download"
                    >
                        <Download size={15} />
                    </a>
                    <button
                        onClick={onClose}
                        title="Close (Esc)"
                        style={{ padding: '6px', borderRadius: '8px', background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
                    >
                        <X size={16} />
                    </button>
                </div>

                {/* PDF content */}
                <div style={{ flex: 1, overflow: 'hidden', background: '#475569' }}>
                    <iframe
                        ref={iframeRef}
                        src={`${url}#toolbar=1&navpanes=0`}
                        style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
                        title={name}
                    />
                </div>

                {/* Footer */}
                <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '24px',
                    padding: '8px 16px', background: '#0f172a', borderRadius: '0 0 20px 20px',
                    flexShrink: 0,
                }}>
                    {[['Esc', 'Close'], ['↓', 'Download']].map(([key, label]) => (
                        <span key={key} style={{ fontSize: '11px', color: '#475569' }}>
                            <kbd style={{
                                background: '#1e293b', color: '#94a3b8', padding: '2px 6px',
                                borderRadius: '4px', fontSize: '10px', fontFamily: 'monospace', marginRight: '4px',
                            }}>{key}</kbd>
                            {label}
                        </span>
                    ))}
                </div>
            </div>
        </div>
    );
}
