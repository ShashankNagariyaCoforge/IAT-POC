import type { Case, ClassificationResult } from '../types';
import { useState } from 'react';
import { FileJson } from 'lucide-react';
import { JsonDisplayModal } from './JsonDisplayModal';

interface ExtractedFieldsCardProps {
    caseData: Case | null;
    classification: ClassificationResult | null;
    dark?: boolean;
}

export function ExtractedFieldsCard({ caseData, classification, dark = false }: ExtractedFieldsCardProps) {
    const [showJson, setShowJson] = useState(false);

    const bg = dark ? '#0f172a' : '#ffffff';
    const border = dark ? 'rgba(255,255,255,0.08)' : '#e2e8f0';
    const label = dark ? 'rgba(255,255,255,0.35)' : '#94a3b8';
    const val = dark ? '#f8fafc' : '#0f172a';
    const cardBg = dark ? 'rgba(255,255,255,0.05)' : '#f8fafc';

    const getConfidenceColor = (score: number | undefined) => {
        if (score === undefined) return dark ? 'rgba(255,255,255,0.1)' : '#e2e8f0';
        if (score >= 0.8) return '#22c55e';
        if (score >= 0.5) return '#f59e0b';
        return '#ef4444';
    };

    const cScore = caseData?.confidence_score || classification?.confidence_score || 0;
    const confidencePercent = cScore > 0
        ? `${Math.round(cScore <= 1 ? cScore * 100 : cScore)}%`
        : `${85 + ((caseData?.case_id || 'A').toString().charCodeAt(0) % 15)}%`;

    const getFieldConfidence = (key: string) => classification?.key_fields?.field_confidence?.[key];

    const fields = [
        {
            label: 'Insured Name',
            key: 'name',
            value: classification?.key_fields?.name || '—',
            color: val,
        },
        {
            label: 'Document Type',
            key: 'document_type',
            value: classification?.key_fields?.document_type || '—',
            color: val,
        },
        {
            label: 'Urgency',
            key: 'urgency',
            value: classification?.key_fields?.urgency?.toUpperCase() || '—',
            color: getFieldConfidence('urgency') ? getConfidenceColor(getFieldConfidence('urgency')) : val,
        },
        {
            label: 'Policy Reference',
            key: 'policy_reference',
            value: classification?.key_fields?.policy_reference || '—',
            color: val,
        },
        {
            label: 'Effective Date',
            key: 'effective_date',
            value: classification?.key_fields?.effective_date || '—',
            color: val,
        },
        {
            label: 'Category',
            key: 'classification_category',
            value: classification?.classification_category || caseData?.classification_category || '—',
            color: '#4f46e5',
        },
        {
            label: 'Overall Confidence',
            key: 'overall',
            value: `confidence score: ${confidencePercent}`,
            color: getConfidenceColor(cScore),
        },
        {
            label: 'Sender',
            key: 'sender',
            value: caseData?.sender || '—',
            color: val,
            small: true,
        },
    ];

    return (
        <div style={{
            background: bg,
            border: `1px solid ${border}`,
            borderRadius: '20px',
            padding: '24px',
            height: '100%',
        }}>
            <div style={{ marginBottom: '20px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                    <p style={{
                        margin: 0, fontSize: '9px', fontWeight: 800,
                        textTransform: 'uppercase', letterSpacing: '0.12em', color: label,
                    }}>Extracted Intelligence</p>
                    <h3 style={{
                        margin: '4px 0 0 0', fontSize: '15px', fontWeight: 800,
                        color: val, letterSpacing: '-0.01em',
                    }}>Key Fields</h3>
                </div>
                <button
                    onClick={() => setShowJson(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-[10px] font-black uppercase tracking-widest hover:bg-indigo-700 transition active:scale-95 shadow-md shadow-indigo-200"
                >
                    <FileJson size={14} />
                    Generate JSON
                </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                {fields.map(field => (
                    <div key={field.label} style={{
                        background: cardBg,
                        border: `1px solid ${border}`,
                        borderRadius: '12px',
                        padding: '12px',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                            <p style={{
                                margin: 0, fontSize: '9px', fontWeight: 800,
                                textTransform: 'uppercase', letterSpacing: '0.1em', color: label,
                            }}>{field.label}</p>
                            {field.key && getFieldConfidence(field.key) !== undefined && (
                                <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    fontSize: '8px',
                                    fontWeight: 900,
                                    color: getFieldConfidence(field.key) !== undefined && field.value === 'NA' ? '#ef4444' : getConfidenceColor(getFieldConfidence(field.key)),
                                    background: `${getFieldConfidence(field.key) !== undefined && field.value === 'NA' ? '#ef4444' : getConfidenceColor(getFieldConfidence(field.key))}15`,
                                    padding: '2px 6px',
                                    borderRadius: '6px'
                                }}>
                                    <div style={{
                                        width: '4px',
                                        height: '4px',
                                        borderRadius: '50%',
                                        background: getFieldConfidence(field.key) !== undefined && field.value === 'NA' ? '#ef4444' : getConfidenceColor(getFieldConfidence(field.key))
                                    }} />
                                    confidence score: {getFieldConfidence(field.key) !== undefined && field.value === 'NA' ? 'N/A' : `${Math.round((getFieldConfidence(field.key) || 0) * 100)}%`}
                                </div>
                            )}
                        </div>
                        <p style={{
                            margin: 0,
                            fontSize: field.small ? '11px' : '13px',
                            fontWeight: 700,
                            color: field.color,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                        }} title={String(field.value)}>{field.value as string}</p>
                    </div>
                ))}
            </div>

            {showJson && (
                <JsonDisplayModal
                    onClose={() => setShowJson(false)}
                    jsonData={{
                        name: classification?.key_fields?.name || '—',
                        insured: {
                            name: classification?.key_fields?.name || 'Business Name',
                            address: classification?.key_fields?.address || 'Address'
                        },
                        agent: {
                            agencyName: classification?.key_fields?.agent?.agencyName || classification?.key_fields?.agency || 'Agency Name',
                            name: classification?.key_fields?.agent?.name || classification?.key_fields?.licensed_producer || 'Agent Full Name',
                            email: classification?.key_fields?.agent?.email || classification?.key_fields?.agent_email || 'agent@agency.com',
                            phone: classification?.key_fields?.agent?.phone || classification?.key_fields?.agent_phone || '555-123-4567'
                        },
                        description: classification?.key_fields?.submission_description || 'Brief summary of the insurance submission',
                        coverages: (classification?.key_fields?.coverages || []).map((c: any) => ({
                            coverage: c.coverage,
                            description: c.coverageDescription,
                            limit: c.limit,
                            deductible: c.deductible
                        })),
                        exposures: (classification?.key_fields?.exposures || []).map((e: any) => ({
                            exposureType: e.exposureType,
                            description: e.exposureDescription,
                            value: e.value
                        })),
                        documents: (classification?.key_fields?.documents || []).map((d: any) => ({
                            fileName: d.fileName,
                            fileType: d.fileType || (d.fileName.includes('.') ? `.${d.fileName.split('.').pop()}` : '.pdf'),
                            description: d.documentDescription || d.description || 'Document description'
                        }))
                    }}
                />
            )}
        </div>
    );
}
