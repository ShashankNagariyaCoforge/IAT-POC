import React from 'react';
import { format } from 'date-fns';
import { AlertTriangle, CheckCircle, Clock, Mail, Zap } from 'lucide-react';
import { ConfidenceMeter } from './ConfidenceMeter';
import type { Case, TimelineEvent } from '../types';

interface CaseSummaryPanelProps {
    caseData: Case;
    timeline: TimelineEvent[];
}

const EVENT_ICON: Record<string, React.ReactNode> = {
    'Email received': <Mail className="w-3.5 h-3.5" style={{ color: '#00467F' }} />,
    'Email classified': <Zap className="w-3.5 h-3.5" style={{ color: '#22c55e' }} />,
    'Downstream notification sent': <CheckCircle className="w-3.5 h-3.5" style={{ color: '#22c55e' }} />,
};

const card: React.CSSProperties = {
    background: '#ffffff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '20px',
};

export function CaseSummaryPanel({ caseData, timeline }: CaseSummaryPanelProps) {
    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '20px' }}>
            {/* AI Summary */}
            <div style={{ ...card, gridColumn: '1 / 3' }}>
                <h3 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 12px 0' }}>AI Summary</h3>
                <p style={{ color: '#333', fontSize: '14px', lineHeight: 1.7, margin: 0 }}>
                    {caseData.summary || 'Summary not yet available. Classification may still be in progress.'}
                </p>
                {caseData.requires_human_review && (
                    <div style={{ marginTop: '16px', display: 'flex', alignItems: 'center', gap: '8px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '6px', padding: '8px 12px' }}>
                        <AlertTriangle className="w-4 h-4" style={{ color: '#f59e0b', flexShrink: 0 }} />
                        <span style={{ color: '#92400e', fontSize: '13px' }}>This case requires human review (confidence below threshold).</span>
                    </div>
                )}
            </div>

            {/* Case Details */}
            <div style={card}>
                <h3 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 16px 0' }}>Case Details</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                    {[
                        { label: 'Case ID', value: caseData.case_id },
                        { label: 'Subject', value: caseData.subject || '—' },
                        { label: 'Sender', value: caseData.sender },
                        { label: 'Email Count', value: caseData.email_count.toString() },
                        { label: 'Routing', value: caseData.routing_recommendation || '—' },
                        { label: 'Created', value: format(new Date(caseData.created_at), 'dd MMM yyyy HH:mm') },
                    ].map(field => (
                        <div key={field.label}>
                            <p style={{ color: '#8fa1b0', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 2px 0' }}>{field.label}</p>
                            <p style={{ color: '#00263E', fontSize: '13px', fontWeight: 500, margin: 0 }} title={field.value}>{field.value}</p>
                        </div>
                    ))}
                    <div>
                        <p style={{ color: '#8fa1b0', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.04em', margin: '0 0 4px 0' }}>Confidence</p>
                        <ConfidenceMeter score={caseData.confidence_score} />
                    </div>
                </div>
            </div>

            {/* Timeline */}
            <div style={{ ...card, gridColumn: '1 / 4' }}>
                <h3 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 16px 0' }}>Processing Timeline</h3>
                {timeline.length === 0 ? (
                    <p style={{ color: '#8fa1b0', fontSize: '13px', margin: 0 }}>No events recorded yet.</p>
                ) : (
                    <ol style={{ listStyle: 'none', margin: 0, padding: '0 0 0 16px', borderLeft: '2px solid #D1D9E0', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                        {timeline.map((event, i) => (
                            <li key={i} style={{ position: 'relative', marginLeft: '4px' }}>
                                <div style={{
                                    position: 'absolute', left: '-20px', top: '4px',
                                    width: '12px', height: '12px', background: '#e8f0fa',
                                    border: '2px solid #D1D9E0', borderRadius: '50%',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <div style={{ width: '5px', height: '5px', background: '#00467F', borderRadius: '50%' }} />
                                </div>
                                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', paddingLeft: '4px' }}>
                                    {EVENT_ICON[event.event] || <Clock className="w-3.5 h-3.5" style={{ color: '#8fa1b0', marginTop: '2px' }} />}
                                    <div>
                                        <p style={{ color: '#00263E', fontSize: '13px', fontWeight: 500, margin: 0 }}>{event.event}</p>
                                        {event.details && <p style={{ color: '#5a7184', fontSize: '12px', margin: '2px 0 0 0' }}>{event.details}</p>}
                                        {event.timestamp && (
                                            <p style={{ color: '#8fa1b0', fontSize: '11px', margin: '2px 0 0 0' }}>
                                                {format(new Date(event.timestamp), 'dd MMM HH:mm:ss')}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>
                )}
            </div>
        </div>
    );
}
