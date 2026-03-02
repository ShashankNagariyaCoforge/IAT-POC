
import { format } from 'date-fns';
import { CheckCircle2, Clock, AlertTriangle } from 'lucide-react';
import { ConfidenceMeter } from './ConfidenceMeter';
import { CategoryBadge } from './CategoryBadge';
import type { ClassificationResult } from '../types';

interface ClassificationPanelProps {
    classification: ClassificationResult | null;
}

const card: React.CSSProperties = {
    background: '#ffffff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '20px',
};
const label: React.CSSProperties = {
    color: '#8fa1b0', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px',
};
const value: React.CSSProperties = { color: '#00263E', fontSize: '14px' };

export function ClassificationPanel({ classification }: ClassificationPanelProps) {
    if (!classification) {
        return (
            <div style={{ ...card, padding: '48px', textAlign: 'center', color: '#8fa1b0' }}>
                Classification not yet available. Processing may still be in progress.
            </div>
        );
    }

    const urgencyColor = {
        high: '#ef4444',
        medium: '#f59e0b',
        low: '#22c55e',
    }[classification.key_fields?.urgency ?? 'low'] ?? '#8fa1b0';

    return (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
            {/* Main classification */}
            <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <div>
                    <p style={label}>Classification</p>
                    <CategoryBadge category={classification.classification_category} />
                </div>
                <div>
                    <p style={label}>Confidence Score</p>
                    <div style={{ maxWidth: '240px' }}>
                        <ConfidenceMeter score={classification.confidence_score} />
                    </div>
                    <p style={{ color: '#8fa1b0', fontSize: '11px', marginTop: '4px' }}>
                        Threshold: 75% — {classification.requires_human_review
                            ? 'Below threshold, human review recommended'
                            : 'Above threshold'}
                    </p>
                </div>
                {classification.requires_human_review && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '6px', padding: '8px 12px' }}>
                        <AlertTriangle className="w-4 h-4" style={{ color: '#f59e0b', flexShrink: 0 }} />
                        <span style={{ color: '#92400e', fontSize: '13px' }}>Human review required</span>
                    </div>
                )}
                <div>
                    <p style={label}>Routing Recommendation</p>
                    <p style={value}>{classification.routing_recommendation || '—'}</p>
                </div>
                <div>
                    <p style={label}>Summary</p>
                    <p style={{ ...value, lineHeight: 1.6 }}>{classification.summary}</p>
                </div>
            </div>

            {/* Right column */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {/* Key fields */}
                <div style={card}>
                    <h4 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 16px 0' }}>Extracted Key Fields</h4>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                        {[
                            { label: 'Document Type', value: classification.key_fields?.document_type || '—', color: '#00263E' },
                            { label: 'Urgency', value: classification.key_fields?.urgency || '—', color: urgencyColor },
                            { label: 'Policy Reference', value: classification.key_fields?.policy_reference || '—', color: '#00263E' },
                            { label: 'Claim Type', value: classification.key_fields?.claim_type || '—', color: '#00263E' },
                        ].map(field => (
                            <div key={field.label}>
                                <p style={label}>{field.label}</p>
                                <p style={{ ...value, color: field.color, fontWeight: 500 }}>{field.value}</p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Downstream notification */}
                <div style={card}>
                    <h4 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 12px 0' }}>Downstream Notification</h4>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        {classification.downstream_notification_sent ? (
                            <>
                                <CheckCircle2 className="w-5 h-5" style={{ color: '#22c55e', flexShrink: 0 }} />
                                <div>
                                    <p style={{ color: '#15803d', fontSize: '13px', fontWeight: 500, margin: 0 }}>Notification sent</p>
                                    {classification.downstream_notification_at && (
                                        <p style={{ color: '#8fa1b0', fontSize: '11px', margin: '2px 0 0 0' }}>
                                            {format(new Date(classification.downstream_notification_at), 'dd MMM yyyy HH:mm:ss')}
                                        </p>
                                    )}
                                </div>
                            </>
                        ) : (
                            <>
                                <Clock className="w-5 h-5" style={{ color: '#8fa1b0', flexShrink: 0 }} />
                                <p style={{ color: '#8fa1b0', fontSize: '13px', margin: 0 }}>Notification pending</p>
                            </>
                        )}
                    </div>
                </div>

                {/* Meta */}
                <div style={card}>
                    <h4 style={{ color: '#00263E', fontSize: '13px', fontWeight: 600, margin: '0 0 12px 0' }}>Classification Metadata</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: '#8fa1b0', fontSize: '12px' }}>Result ID</span>
                            <span style={{ color: '#00263E', fontSize: '12px', fontFamily: 'monospace' }}>{classification.result_id.slice(0, 8)}…</span>
                        </div>
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ color: '#8fa1b0', fontSize: '12px' }}>Classified At</span>
                            <span style={{ color: '#00263E', fontSize: '12px' }}>
                                {format(new Date(classification.classified_at), 'dd MMM yyyy HH:mm:ss')}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
