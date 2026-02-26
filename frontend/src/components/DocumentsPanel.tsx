import React, { useState } from 'react';
import { FileText, Link, Eye, EyeOff, CheckCircle2, XCircle } from 'lucide-react';
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
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
                No documents found for this case.
            </div>
        );
    }

    return (
        <div className="space-y-3">
            {documents.map(doc => {
                const isOpen = previewId === doc.document_id;
                const icon = FILE_TYPE_ICONS[doc.file_type.toLowerCase()] || '📎';
                return (
                    <div key={doc.document_id} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
                        <div className="flex items-start gap-3">
                            <span className="text-2xl flex-shrink-0">{icon}</span>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-2 flex-wrap">
                                    <span className="text-slate-200 text-sm font-medium truncate">{doc.file_name}</span>
                                    <span className="text-xs text-slate-500 uppercase bg-slate-800 px-1.5 py-0.5 rounded">
                                        {doc.file_type}
                                    </span>
                                    {/* OCR indicator */}
                                    {doc.ocr_applied && (
                                        <span className="text-xs text-purple-300 bg-purple-900/40 px-1.5 py-0.5 rounded flex items-center gap-1">
                                            <Eye className="w-3 h-3" /> OCR
                                        </span>
                                    )}
                                    {/* URL crawl indicator */}
                                    {doc.has_urls && (
                                        <span className="text-xs text-blue-300 bg-blue-900/40 px-1.5 py-0.5 rounded flex items-center gap-1">
                                            <Link className="w-3 h-3" /> {doc.crawled_urls.length} URL{doc.crawled_urls.length !== 1 ? 's' : ''}
                                        </span>
                                    )}
                                    {/* Processing status */}
                                    <span className={`text-xs px-1.5 py-0.5 rounded flex items-center gap-1
                    ${doc.processing_status === 'DONE'
                                            ? 'text-green-300 bg-green-900/40'
                                            : 'text-red-300 bg-red-900/40'}`}>
                                        {doc.processing_status === 'DONE'
                                            ? <><CheckCircle2 className="w-3 h-3" /> Processed</>
                                            : <><XCircle className="w-3 h-3" /> {doc.processing_status}</>}
                                    </span>
                                </div>

                                {doc.extracted_text_preview && (
                                    <button
                                        onClick={() => setPreviewId(isOpen ? null : doc.document_id)}
                                        className="flex items-center gap-1.5 text-slate-400 hover:text-white text-xs transition-colors"
                                    >
                                        {isOpen ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                                        {isOpen ? 'Hide' : 'Preview extracted text'}
                                    </button>
                                )}
                            </div>
                        </div>

                        {isOpen && doc.extracted_text_preview && (
                            <div className="mt-3 bg-slate-800 border border-slate-700 rounded-lg p-4">
                                <div className="flex items-center justify-between mb-2">
                                    <span className="text-slate-400 text-xs uppercase tracking-wider font-medium">
                                        Extracted Text Preview (PII masked)
                                    </span>
                                </div>
                                <pre className="text-slate-300 text-xs font-mono whitespace-pre-wrap leading-relaxed">
                                    {doc.extracted_text_preview}
                                    {doc.extracted_text_preview.length >= 500 && (
                                        <span className="text-slate-600"> …[truncated]</span>
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
