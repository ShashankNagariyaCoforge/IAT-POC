import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import { ChevronDown, ChevronUp, Paperclip, Mail, User } from 'lucide-react';
import type { Email, Document } from '../types';
import { HtmlSandbox } from './HtmlSandbox';

interface EmailChainPanelProps {
    emails: Email[];
    documents?: Document[];
    onDocumentClick?: (doc: Document) => void;
}

export function EmailChainPanel({ emails, documents = [], onDocumentClick }: EmailChainPanelProps) {
    // Newest emails first, then reverse for display so first one is expanded
    const sortedEmails = [...emails].sort((a, b) =>
        new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
    );

    const [expanded, setExpanded] = useState<Set<string>>(new Set());
    const [lastCaseId, setLastCaseId] = useState<string | null>(null);

    // Only auto-expand the newest email when we switch to a DIFFERENT case
    const currentCaseId = emails.length > 0 ? emails[0].case_id : null;

    useEffect(() => {
        if (currentCaseId !== lastCaseId) {
            if (sortedEmails.length > 0) {
                setExpanded(new Set([sortedEmails[0].email_id]));
            } else {
                setExpanded(new Set());
            }
            setLastCaseId(currentCaseId);
        }
    }, [currentCaseId, lastCaseId, sortedEmails]);

    const toggle = (id: string) =>
        setExpanded(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });

    /**
     * Attempts to strip "Original Message" history from email content.
     */
    const cleanThreadContent = (html: string) => {
        if (!html) return '';
        const separators = [
            /<div[^>]*class=["'](?:gmail_quote|outlook_signature|append_to_reply)["'][^>]*>/i,
            /<hr[^>]*>\s*<b>From:<\/b>/i,
            /-----Original Message-----/i,
            /________________________________/i,
            /\nFrom: /i,
            /On\s.*\swrote:/i
        ];
        let cleaned = html;
        for (const sep of separators) {
            const match = cleaned.split(sep);
            if (match.length > 1) cleaned = match[0];
        }
        return cleaned.trim();
    };

    if (emails.length === 0) {
        return (
            <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center text-slate-400">
                <Mail size={32} className="mx-auto mb-4 opacity-20" />
                <p className="font-semibold text-slate-500">No communication history found</p>
            </div>
        );
    }

    return (
        <div className="flex flex-col gap-4">
            {sortedEmails.map((email, idx) => {
                const isOpen = expanded.has(email.email_id);
                const isNewest = idx === 0;

                return (
                    <div
                        key={email.email_id}
                        className={`bg-white border rounded-2xl overflow-hidden transition-all duration-200 shadow-sm ${isOpen ? 'border-indigo-200 ring-1 ring-indigo-50' : 'border-slate-200 hover:border-slate-300'
                            }`}
                    >
                        {/* Header */}
                        <button
                            onClick={() => toggle(email.email_id)}
                            className={`w-full flex items-start gap-4 p-5 text-left transition-colors ${isOpen ? 'bg-indigo-50/30' : 'bg-white'
                                }`}
                        >
                            <div className={`flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm ${isNewest ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-600'
                                }`}>
                                <User size={18} />
                            </div>

                            <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-4 mb-1">
                                    <span className="text-slate-950 font-bold truncate text-[14px]">
                                        {email.sender}
                                    </span>
                                    <span className="text-slate-400 text-[11px] font-semibold whitespace-nowrap">
                                        {format(new Date(email.received_at), 'MMM dd, yyyy · HH:mm')}
                                    </span>
                                </div>
                                <div className="flex items-center gap-2 mb-1">
                                    <p className="text-slate-600 text-[13px] font-medium truncate">
                                        {email.subject || '(No subject)'}
                                    </p>
                                    {email.has_attachments && (
                                        <div className="flex items-center gap-1 px-1.5 py-0.5 bg-slate-100 rounded text-[10px] font-bold text-slate-500">
                                            <Paperclip size={10} /> {email.attachment_count}
                                        </div>
                                    )}
                                </div>
                                {!isOpen && email.body_preview && (
                                    <p className="text-slate-400 text-[12px] truncate italic">
                                        {email.body_preview.substring(0, 100)}...
                                    </p>
                                )}
                            </div>

                            <div className="mt-1">
                                {isOpen ? <ChevronUp size={18} className="text-slate-300" /> : <ChevronDown size={18} className="text-slate-300" />}
                            </div>
                        </button>

                        {/* Body */}
                        {isOpen && (
                            <div className="px-5 pb-6 border-t border-slate-100 pt-6">
                                <HtmlSandbox html={cleanThreadContent(email.body)} className="min-h-[100px]" />

                                {documents.filter(d => d.email_id === email.email_id).length > 0 && (
                                    <div className="mt-8 pt-6 border-t border-slate-100">
                                        <h5 className="text-[11px] font-black text-slate-400 uppercase tracking-widest mb-3 flex items-center gap-2">
                                            <Paperclip size={12} /> Attachments Received ({documents.filter(d => d.email_id === email.email_id).length})
                                        </h5>
                                        <div className="flex flex-wrap gap-2">
                                            {documents.filter(d => d.email_id === email.email_id).map((doc, dIdx) => {
                                                const ext = (doc.file_name || '').split('.').pop()?.toLowerCase() || '';
                                                const iconStyles: Record<string, { bg: string; text: string; label: string }> = {
                                                    pdf:  { bg: 'bg-red-50',     text: 'text-red-500',    label: 'PDF'  },
                                                    docx: { bg: 'bg-blue-50',    text: 'text-blue-600',   label: 'DOC' },
                                                    doc:  { bg: 'bg-blue-50',    text: 'text-blue-600',   label: 'DOC' },
                                                    xlsx: { bg: 'bg-emerald-50', text: 'text-emerald-600',label: 'XLS' },
                                                    xls:  { bg: 'bg-emerald-50', text: 'text-emerald-600',label: 'XLS' },
                                                    jpg:  { bg: 'bg-purple-50',  text: 'text-purple-500', label: 'IMG' },
                                                    jpeg: { bg: 'bg-purple-50',  text: 'text-purple-500', label: 'IMG' },
                                                    png:  { bg: 'bg-purple-50',  text: 'text-purple-500', label: 'IMG' },
                                                    tiff: { bg: 'bg-purple-50',  text: 'text-purple-500', label: 'IMG' },
                                                    tif:  { bg: 'bg-purple-50',  text: 'text-purple-500', label: 'IMG' },
                                                    eml:  { bg: 'bg-amber-50',   text: 'text-amber-600',  label: 'EML' },
                                                    msg:  { bg: 'bg-amber-50',   text: 'text-amber-600',  label: 'MSG' },
                                                };
                                                const ic = iconStyles[ext] || { bg: 'bg-slate-100', text: 'text-slate-500', label: (ext.toUpperCase() || 'FILE').slice(0, 4) };
                                                return (
                                                    <button
                                                        key={dIdx}
                                                        onClick={() => onDocumentClick?.(doc)}
                                                        className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg hover:border-indigo-300 hover:bg-white hover:text-indigo-700 transition-all text-sm font-semibold text-slate-600"
                                                    >
                                                        <div className={`w-6 h-6 ${ic.bg} ${ic.text} rounded flex items-center justify-center text-[8px] font-black`}>
                                                            {ic.label}
                                                        </div>
                                                        {doc.file_name}
                                                    </button>
                                                );
                                            })}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
