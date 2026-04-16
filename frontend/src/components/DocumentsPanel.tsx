import { useState } from 'react';
import { Link, Eye, EyeOff, CheckCircle2, XCircle, ExternalLink } from 'lucide-react';
import type { Document } from '../types';

interface DocumentsPanelProps {
    documents: Document[];
    caseId: string;
}

// SVG icon config — mirrors CaseActionScreen document bundle section
const iconConfig: Record<string, { bg: string; border: string; text: string; icon: JSX.Element }> = {
    pdf:  { bg: 'bg-red-50',    border: 'border-red-100',    text: 'text-red-500',    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg> },
    xlsx: { bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg> },
    xls:  { bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg> },
    docx: { bg: 'bg-blue-50',    border: 'border-blue-100',    text: 'text-blue-600',   icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg> },
    doc:  { bg: 'bg-blue-50',    border: 'border-blue-100',    text: 'text-blue-600',   icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg> },
    jpg:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
    jpeg: { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
    png:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
    tiff: { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
    tif:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
    eml:  { bg: 'bg-amber-50',   border: 'border-amber-100',   text: 'text-amber-600',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> },
    msg:  { bg: 'bg-amber-50',   border: 'border-amber-100',   text: 'text-amber-600',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> },
    txt:  { bg: 'bg-slate-50',   border: 'border-slate-200',   text: 'text-slate-400',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/><line x1="9" y1="9" x2="11" y2="9"/></svg> },
};

const fallbackIcon = {
    bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-400',
    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width: 16, height: 16 }}><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>,
};

// Extensions that use /view endpoint (non-PDF files the browser can't natively display as PDF)
const VIEW_EXTENSIONS = new Set(['xlsx', 'xls', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'gif', 'webp', 'docx', 'doc']);

export function DocumentsPanel({ documents, caseId }: DocumentsPanelProps) {
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
                // Derive extension from file_name (reliable) not file_type (often wrong)
                const fileName = doc.file_name || (doc as any).filename || '';
                const ext = fileName.split('.').pop()?.toLowerCase() || '';
                const ic = iconConfig[ext] || fallbackIcon;
                const endpoint = VIEW_EXTENSIONS.has(ext) ? 'view' : 'pdf';
                const docUrl = `/api/cases/${caseId}/documents/${doc.document_id}/${endpoint}`;

                return (
                    <div key={doc.document_id} style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '16px' }}>
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                            {/* Extension icon — same style as CaseActionScreen document bundle */}
                            <div className={`${ic.bg} ${ic.text} ${ic.border}`} style={{
                                width: 36, height: 36, border: '1px solid', borderRadius: 8,
                                display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                            }}>
                                {ic.icon}
                            </div>

                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
                                    <span style={{ color: '#00263E', fontSize: '13px', fontWeight: 500 }}>{fileName}</span>
                                    <span style={{ fontSize: '11px', color: '#8fa1b0', background: '#F4F6F8', padding: '2px 6px', borderRadius: '4px', textTransform: 'uppercase' }}>
                                        {ext || doc.file_type}
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

                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                                    {/* Open document in new tab */}
                                    <a
                                        href={docUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', color: '#4f46e5', fontSize: '12px', fontWeight: 500, textDecoration: 'none' }}
                                    >
                                        <ExternalLink style={{ width: 12, height: 12 }} /> Open document
                                    </a>

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
