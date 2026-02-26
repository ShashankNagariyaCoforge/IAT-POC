import React, { useState } from 'react';
import { format } from 'date-fns';
import { ChevronDown, ChevronRight, Paperclip, Mail } from 'lucide-react';
import type { Email } from '../types';

interface EmailChainPanelProps {
    emails: Email[];
}

export function EmailChainPanel({ emails }: EmailChainPanelProps) {
    const [expanded, setExpanded] = useState<Set<string>>(new Set());

    const toggle = (id: string) =>
        setExpanded(prev => {
            const next = new Set(prev);
            next.has(id) ? next.delete(id) : next.add(id);
            return next;
        });

    if (emails.length === 0) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
                No emails found for this case.
            </div>
        );
    }

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl divide-y divide-slate-800 overflow-hidden">
            {emails.map((email, idx) => {
                const isOpen = expanded.has(email.email_id);
                return (
                    <div key={email.email_id}>
                        <button
                            onClick={() => toggle(email.email_id)}
                            className="w-full flex items-start gap-3 px-5 py-4 hover:bg-slate-800/50 transition-colors text-left"
                        >
                            <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-900/50 flex items-center justify-center text-blue-400 text-xs font-semibold mt-0.5">
                                {idx + 1}
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="text-slate-200 text-sm font-medium truncate">{email.sender}</span>
                                    <span className="text-slate-600 text-xs">→</span>
                                    <span className="text-slate-400 text-xs truncate">{email.recipients.join(', ')}</span>
                                </div>
                                <p className="text-slate-300 text-sm truncate">{email.subject || '(No subject)'}</p>
                                <p className="text-slate-500 text-xs mt-0.5">
                                    {format(new Date(email.received_at), 'dd MMM yyyy HH:mm')}
                                    {email.has_attachments && (
                                        <span className="ml-2 inline-flex items-center gap-1">
                                            <Paperclip className="w-3 h-3" />{email.attachment_count}
                                        </span>
                                    )}
                                </p>
                            </div>
                            {isOpen
                                ? <ChevronDown className="w-4 h-4 text-slate-500 flex-shrink-0 mt-1" />
                                : <ChevronRight className="w-4 h-4 text-slate-500 flex-shrink-0 mt-1" />}
                        </button>
                        {isOpen && email.body_preview && (
                            <div className="px-5 pb-5 pl-15">
                                <div className="bg-slate-800 rounded-lg p-4 text-slate-300 text-sm leading-relaxed font-mono whitespace-pre-wrap border border-slate-700 ml-10">
                                    {email.body_preview}
                                    <span className="text-slate-600"> [PII masked]</span>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
