import { useState } from 'react';
import { format } from 'date-fns';
import { ChevronDown, ChevronRight, Paperclip } from 'lucide-react';
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
            <div style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '48px', textAlign: 'center', color: '#8fa1b0' }}>
                No emails found for this case.
            </div>
        );
    }

    return (
        <div style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', overflow: 'hidden' }}>
            {emails.map((email, idx) => {
                const isOpen = expanded.has(email.email_id);
                return (
                    <div key={email.email_id} style={{ borderBottom: idx < emails.length - 1 ? '1px solid #eef1f4' : 'none' }}>
                        <button
                            onClick={() => toggle(email.email_id)}
                            style={{
                                width: '100%', display: 'flex', alignItems: 'flex-start', gap: '12px',
                                padding: '16px 20px', background: 'none', border: 'none', cursor: 'pointer',
                                textAlign: 'left', transition: 'background 0.15s',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.background = '#f0f5fb')}
                            onMouseLeave={e => (e.currentTarget.style.background = 'none')}
                        >
                            <div style={{
                                flexShrink: 0, width: '28px', height: '28px', borderRadius: '50%',
                                background: '#e8f0fa', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: '#00467F', fontSize: '12px', fontWeight: 600, marginTop: '2px',
                            }}>
                                {idx + 1}
                            </div>
                            <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                                    <span style={{ color: '#00263E', fontSize: '13px', fontWeight: 500 }}>{email.sender}</span>
                                    <span style={{ color: '#D1D9E0' }}>→</span>
                                    <span style={{ color: '#8fa1b0', fontSize: '12px' }}>{email.recipients.join(', ')}</span>
                                </div>
                                <p style={{ color: '#00263E', fontSize: '13px', margin: '0 0 4px 0' }}>{email.subject || '(No subject)'}</p>
                                <p style={{ color: '#8fa1b0', fontSize: '11px', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                                    {format(new Date(email.received_at), 'dd MMM yyyy HH:mm')}
                                    {email.has_attachments && (
                                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                            <Paperclip className="w-3 h-3" /> {email.attachment_count}
                                        </span>
                                    )}
                                </p>
                            </div>
                            {isOpen
                                ? <ChevronDown className="w-4 h-4" style={{ color: '#8fa1b0', flexShrink: 0, marginTop: '4px' }} />
                                : <ChevronRight className="w-4 h-4" style={{ color: '#8fa1b0', flexShrink: 0, marginTop: '4px' }} />}
                        </button>
                        {isOpen && email.body_preview && (
                            <div style={{ padding: '0 20px 16px 60px' }}>
                                <div style={{
                                    background: '#F4F6F8', border: '1px solid #D1D9E0', borderRadius: '6px',
                                    padding: '16px', fontSize: '12px', fontFamily: 'monospace',
                                    whiteSpace: 'pre-wrap', lineHeight: 1.6, color: '#00263E',
                                }}>
                                    {email.body_preview}
                                    <span style={{ color: '#8fa1b0' }}> [PII masked]</span>
                                </div>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
