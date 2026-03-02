import { useState } from 'react';
import { Link, Eye, EyeOff, CheckCircle2, XCircle } from 'lucide-react';
import type { Document } from '../types';

interface DocumentsPanelProps {
    documents: Document[];
}

const FILE_TYPE_ICONS: Record<string, string> = {
    pdf: '📄', docx: '📝', doc: '📝',
    jpg: '🖼️', jpeg: '🖼️', png: '🖼️', tiff: '🖼️',
};

export function DocumentsPanel({ documents }: DocumentsPanelProps) {
    const [previewId, setPreviewId] = useState<string | null>(null);

    if (documents.length === 0) {
        return (
            <div style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '48px', textAlign: 'center', color: '#8fa1b0' }}>
                No documents found for this case.
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {documents.map(doc => {
                const isOpen = previewId === doc.document_id;
                const icon = FILE_TYPE_ICONS[doc.file_type.toLowerCase()] || '📎';
                return (
                    <div key={doc.document_id} style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                            <span style={{ fontSize: '24px', flexShrink: 0 }}>{icon}</span>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
                                    <span style={{ color: '#00263E', fontSize: '13px', fontWeight: 500 }}>{doc.file_name}</span>
                                    <span style={{ fontSize: '11px', color: '#8fa1b0', background: '#F4F6F8', padding: '2px 6px', borderRadius: '4px', textTransform: 'uppercase' }}>
                                        {doc.file_type}
                                    </span>
                                    {doc.ocr_applied && (
                                        <span style={{ fontSize: '11px', color: '#7c3aed', background: '#f5f3ff', padding: '2px 6px', borderRadius: '4px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                            <Eye className="w-3 h-3" /> OCR
                                        </span>
                                    )}
                                    {doc.has_urls && (
                                        <span style={{ fontSize: '11px', color: '#00467F', background: '#e8f0fa', padding: '2px 6px', borderRadius: '4px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                                            <Link className="w-3 h-3" /> {doc.crawled_urls.length} URL{doc.crawled_urls.length !== 1 ? 's' : ''}
                                        </span>
                                    )}
                                    <span style={{
                                        fontSize: '11px', padding: '2px 6px', borderRadius: '4px',
                                        display: 'inline-flex', alignItems: 'center', gap: '4px',
                                        ...(doc.processing_status === 'DONE'
                                            ? { color: '#15803d', background: '#f0fdf4' }
                                            : { color: '#b91c1c', background: '#fff5f5' })
                                    }}>
                                        {doc.processing_status === 'DONE'
                                            ? <><CheckCircle2 className="w-3 h-3" /> Processed</>
                                            : <><XCircle className="w-3 h-3" /> {doc.processing_status}</>}
                                    </span>
                                </div>

                                {doc.extracted_text_preview && (
                                    <button
                                        onClick={() => setPreviewId(isOpen ? null : doc.document_id)}
                                        style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00467F', background: 'none', border: 'none', cursor: 'pointer', fontSize: '12px', fontWeight: 500, padding: 0 }}
                                    >
                                        {isOpen ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                        {isOpen ? 'Hide' : 'Preview extracted text'}
                                    </button>
                                )}
                            </div>
                        </div>

                        {isOpen && doc.extracted_text_preview && (
                            <div style={{ marginTop: '12px', background: '#F4F6F8', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '16px' }}>
                                <p style={{ color: '#8fa1b0', fontSize: '11px', textTransform: 'uppercase', fontWeight: 600, letterSpacing: '0.05em', marginBottom: '8px' }}>
                                    Extracted Text Preview (PII masked)
                                </p>
                                <pre style={{ color: '#00263E', fontSize: '12px', fontFamily: 'monospace', whiteSpace: 'pre-wrap', lineHeight: 1.6, margin: 0 }}>
                                    {doc.extracted_text_preview}
                                    {doc.extracted_text_preview.length >= 500 && (
                                        <span style={{ color: '#8fa1b0' }}> …[truncated]</span>
                                    )}
                                </pre>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
