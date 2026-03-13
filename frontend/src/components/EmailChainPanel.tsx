import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import { ChevronDown, ChevronUp, Paperclip, Mail, User } from 'lucide-react';
import type { Email } from '../types';
import { HtmlSandbox } from './HtmlSandbox';

interface EmailChainPanelProps {
    emails: Email[];
}

export function EmailChainPanel({ emails }: EmailChainPanelProps) {
    // Newest emails first, then reverse for display so first one is expanded
    const sortedEmails = [...emails].sort((a, b) =>
        new Date(b.received_at).getTime() - new Date(a.received_at).getTime()
    );

    const [expanded, setExpanded] = useState<Set<string>>(new Set());

    useEffect(() => {
        if (sortedEmails.length > 0 && expanded.size === 0) {
            setExpanded(new Set([sortedEmails[0].email_id]));
        }
    }, [sortedEmails]);

    const toggle = (id: string) =>
        setExpanded(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });

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
                                <HtmlSandbox html={email.body} className="min-h-[100px]" />
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
