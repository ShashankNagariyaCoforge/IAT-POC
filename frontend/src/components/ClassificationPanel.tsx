import React, { useState, useEffect } from 'react';
import { format } from 'date-fns';
import { CheckCircle2, Clock, AlertTriangle, FileText, ExternalLink, ChevronDown } from 'lucide-react';
import { ConfidenceMeter } from './ConfidenceMeter';
import { CategoryBadge } from './CategoryBadge';
import type { ClassificationResult } from '../types';

interface ClassificationPanelProps {
    caseId: string;
    classification: ClassificationResult | null;
}

const card: React.CSSProperties = {
    background: '#ffffff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '20px',
};
const labelStyle: React.CSSProperties = {
    color: '#8fa1b0', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px',
};
const valueStyle: React.CSSProperties = { color: '#00263E', fontSize: '14px' };

export function ClassificationPanel({ caseId, classification }: ClassificationPanelProps) {
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

    // Update selectedDocId when classification changes
    useEffect(() => {
        if (classification?.annotated_docs) {
            const ids = Object.keys(classification.annotated_docs);
            if (ids.length > 0 && !selectedDocId) {
                setSelectedDocId(ids[0]);
            }
        }
    }, [classification, selectedDocId]);

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

    const annotatedDocIds = Object.keys(classification.annotated_docs || {});
    // Use the explicit selected doc or fall back to the first one available
    const displayDocId = selectedDocId || (annotatedDocIds.length > 0 ? annotatedDocIds[0] : null);
    const annotatedPdfUrl = displayDocId ? `/api/cases/${caseId}/documents/${displayDocId}/annotated` : null;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                {/* Main classification */}
                <div style={{ ...card, display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div>
                        <p style={labelStyle}>Classification</p>
                        <CategoryBadge category={classification.classification_category} />
                    </div>
                    <div>
                        <p style={labelStyle}>Confidence Score</p>
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
                        <p style={labelStyle}>Summary</p>
                        <p style={{ ...valueStyle, lineHeight: 1.6 }}>{classification.summary}</p>
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
                                { label: 'Submission Type', value: classification.key_fields?.submission_type || '—', color: '#00263E' },
                                { label: 'Segment', value: classification.key_fields?.segment || '—', color: '#00263E' },
                                { label: 'Urgency', value: classification.key_fields?.urgency || '—', color: urgencyColor },
                                { label: 'Policy Reference', value: classification.key_fields?.policy_reference || '—', color: '#00263E' },
                            ].map(field => (
                                <div key={field.label}>
                                    <p style={labelStyle}>{field.label}</p>
                                    <p style={{ ...valueStyle, color: field.color, fontWeight: 500 }}>{field.value}</p>
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
                        </div>
                    </div>
                </div>
            </div>

            {/* Document Preview Section */}
            <div style={{ ...card, padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                <div style={{
                    padding: '12px 20px',
                    borderBottom: '1px solid #D1D9E0',
                    background: '#F8FAFC',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <FileText size={16} style={{ color: '#4f46e5' }} />
                            <span style={{ fontSize: '13px', fontWeight: 700, color: '#00263E' }}>Annotated Document Preview</span>
                        </div>

                        {annotatedDocIds.length > 1 && (
                            <div style={{ position: 'relative' }}>
                                <select
                                    value={displayDocId || ''}
                                    onChange={(e) => setSelectedDocId(e.target.value)}
                                    style={{
                                        appearance: 'none',
                                        background: '#fff',
                                        border: '1px solid #D1D9E0',
                                        borderRadius: '6px',
                                        padding: '4px 28px 4px 12px',
                                        fontSize: '12px',
                                        color: '#00263E',
                                        fontWeight: 600,
                                        cursor: 'pointer',
                                        outline: 'none'
                                    }}
                                >
                                    {annotatedDocIds.map(id => (
                                        <option key={id} value={id}>Doc ID: {id.slice(0, 8)}...</option>
                                    ))}
                                </select>
                                <ChevronDown size={14} style={{ position: 'absolute', right: '8px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: '#64748B' }} />
                            </div>
                        )}

                        {displayDocId && (
                            <span style={{
                                fontSize: '10px',
                                background: '#E0E7FF',
                                color: '#4338CA',
                                padding: '2px 6px',
                                borderRadius: '4px',
                                fontWeight: 600,
                            }}>
                                High Fidelity
                            </span>
                        )}
                    </div>
                    {annotatedPdfUrl && (
                        <a
                            href={annotatedPdfUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                fontSize: '12px',
                                color: '#4f46e5',
                                fontWeight: 600,
                                display: 'flex',
                                alignItems: 'center',
                                gap: '4px',
                                textDecoration: 'none'
                            }}
                        >
                            <ExternalLink size={14} />
                            Full View
                        </a>
                    )}
                </div>

                <div style={{ height: '600px', background: '#F1F5F9', position: 'relative' }}>
                    {annotatedPdfUrl ? (
                        <object
                            key={displayDocId} // Force remount on doc change
                            data={`${annotatedPdfUrl}#toolbar=0&navpanes=0&scrollbar=0`}
                            type="application/pdf"
                            style={{ width: '100%', height: '100%' }}
                        >
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748B', gap: '12px' }}>
                                <p style={{ fontSize: '14px' }}>PDF preview not supported by your browser.</p>
                                <a
                                    href={annotatedPdfUrl}
                                    style={{
                                        padding: '8px 16px',
                                        background: '#4f46e5',
                                        color: '#fff',
                                        borderRadius: '8px',
                                        fontWeight: 700,
                                        textDecoration: 'none'
                                    }}
                                >
                                    View Full Document
                                </a>
                            </div>
                        </object>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#94A3B8', gap: '12px' }}>
                            <div style={{ opacity: 0.3 }}><FileText size={48} /></div>
                            <p style={{ fontSize: '14px', fontWeight: 500 }}>No annotated document available for preview.</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
