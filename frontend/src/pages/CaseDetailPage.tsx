import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { ArrowLeft, AlertTriangle, RefreshCw, Download, XCircle } from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { CaseSummaryPanel } from '../components/CaseSummaryPanel';
import { EmailChainPanel } from '../components/EmailChainPanel';
import { DocumentsPanel } from '../components/DocumentsPanel';
import { ClassificationPanel } from '../components/ClassificationPanel';
import { AgentPipelinePanel } from '../components/AgentPipelinePanel';
import { ExtractedFieldsCard } from '../components/ExtractedFieldsCard';
import type { Case, Email, Document, ClassificationResult, TimelineEvent, CaseStatus } from '../types';
import { format } from 'date-fns';

type Panel = 'summary' | 'emails' | 'documents' | 'classification';

// ── Status pill helper ──────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, { bg: string; border: string; color: string; label: string }> = {
    RECEIVED: { bg: '#f0f9ff', border: '#bae6fd', color: '#0369a1', label: 'Received' },
    PROCESSING: { bg: '#eef2ff', border: '#a5b4fc', color: '#4338ca', label: 'Processing' },
    CLASSIFIED: { bg: '#f0fdf4', border: '#86efac', color: '#15803d', label: 'Classified' },
    PROCESSED: { bg: '#f0fdf4', border: '#86efac', color: '#15803d', label: 'Processed' },
    PENDING_REVIEW: { bg: '#fefce8', border: '#fde047', color: '#a16207', label: 'Pending Review' },
    FAILED: { bg: '#fff1f2', border: '#fda4af', color: '#be123c', label: 'Failed' },
    BLOCKED_SAFETY: { bg: '#fff1f2', border: '#fda4af', color: '#be123c', label: 'Blocked' },
    NEEDS_REVIEW_SAFETY: { bg: '#fffbeb', border: '#fcd34d', color: '#b45309', label: 'Safety Review' },
};

const CATEGORY_STYLES: Record<string, { bg: string; border: string; color: string }> = {
    'New': { bg: '#eef2ff', border: '#c7d2fe', color: '#4338ca' },
    'Renewal': { bg: '#f0fdf4', border: '#bbf7d0', color: '#15803d' },
    'Query/General': { bg: '#f0f9ff', border: '#bae6fd', color: '#0284c7' },
    'Follow-up': { bg: '#fdf4ff', border: '#e9d5ff', color: '#7e22ce' },
    'Complaint/Escalation': { bg: '#fff1f2', border: '#fecdd3', color: '#be123c' },
    'Regulatory/Legal': { bg: '#fff7ed', border: '#fed7aa', color: '#c2410c' },
    'Documentation/Evidence': { bg: '#f0fdf4', border: '#bbf7d0', color: '#166534' },
    'Spam/Irrelevant': { bg: '#f8fafc', border: '#cbd5e1', color: '#64748b' },
};

function StatusPill({ status }: { status: CaseStatus }) {
    const st = STATUS_STYLES[status] ?? { bg: '#f8fafc', border: '#e2e8f0', color: '#64748b', label: status };
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '3px 10px', borderRadius: '999px',
            background: st.bg, border: `1px solid ${st.border}`,
            color: st.color, fontSize: '10px', fontWeight: 800,
            textTransform: 'uppercase', letterSpacing: '0.08em',
        }}>{st.label}</span>
    );
}

function CategoryPill({ category }: { category: string | null }) {
    if (!category) return null;
    const cat = CATEGORY_STYLES[category] ?? { bg: '#f8fafc', border: '#e2e8f0', color: '#64748b' };
    return (
        <span style={{
            display: 'inline-block', padding: '3px 10px', borderRadius: '8px',
            background: cat.bg, border: `1px solid ${cat.border}`,
            color: cat.color, fontSize: '10px', fontWeight: 800,
            textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
        }}>{category}</span>
    );
}

export default function CaseDetailPage() {
    const { caseId = '' } = useParams();
    const navigate = useNavigate();
    const { instance } = useMsal();
    const apiClient = createApiClient(instance);

    const [caseData, setCaseData] = useState<Case | null>(null);
    const [emails, setEmails] = useState<Email[]>([]);
    const [documents, setDocuments] = useState<Document[]>([]);
    const [classification, setClassification] = useState<ClassificationResult | null>(null);
    const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
    const [activePanel, setActivePanel] = useState<Panel>('summary');
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const fetchAll = async () => {
        setLoading(true);
        setError(null);
        try {
            const [caseRes, emailsRes, docsRes, classRes, timelineRes] = await Promise.all([
                casesApi.getCase(apiClient, caseId),
                casesApi.getCaseEmails(apiClient, caseId),
                casesApi.getCaseDocuments(apiClient, caseId),
                casesApi.getCaseClassification(apiClient, caseId),
                casesApi.getCaseTimeline(apiClient, caseId),
            ]);
            setCaseData(caseRes);
            setEmails(emailsRes.emails);
            setDocuments(docsRes.documents);
            setClassification(classRes.classification);
            setTimeline(timelineRes.timeline);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to load case.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchAll(); }, [caseId]);

    const tabs: { key: Panel; label: string; count?: number }[] = [
        { key: 'summary', label: 'Summary' },
        { key: 'emails', label: 'Email Chain', count: emails.length },
        { key: 'documents', label: 'Documents', count: documents.length },
        { key: 'classification', label: 'Classification' },
    ];

    // Loading state
    if (loading) return (
        <div style={{ minHeight: '100vh', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
                <RefreshCw size={32} style={{ color: '#4f46e5', animation: 'spin 1s linear infinite', display: 'block', margin: '0 auto 16px' }} />
                <p style={{ color: '#94a3b8', fontSize: '14px', fontWeight: 600, margin: 0 }}>Loading case…</p>
            </div>
        </div>
    );

    if (error) return (
        <div style={{ minHeight: '100vh', background: '#f8fafc', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', maxWidth: '400px' }}>
                <XCircle size={40} style={{ color: '#e11d48', margin: '0 auto 16px', display: 'block' }} />
                <p style={{ color: '#be123c', fontSize: '16px', fontWeight: 700, marginBottom: '8px' }}>Error loading case</p>
                <p style={{ color: '#94a3b8', fontSize: '13px', marginBottom: '20px' }}>{error}</p>
                <button onClick={() => navigate('/')} style={{ color: '#4f46e5', background: '#eef2ff', border: '1px solid #c7d2fe', borderRadius: '10px', padding: '8px 20px', cursor: 'pointer', fontSize: '13px', fontWeight: 700 }}>
                    ← Back to cases
                </button>
            </div>
        </div>
    );

    // ── Blocked Safety full-page view ──────────────────────────────────────
    if (caseData?.status === 'BLOCKED_SAFETY') {
        return (
            <div style={{ minHeight: '100vh', background: '#f8fafc' }}>
                {/* Header */}
                <header style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(226,232,240,0.8)', padding: '0 32px', position: 'sticky', top: 0, zIndex: 50 }}>
                    <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', height: '64px', gap: '16px' }}>
                        <img src="/assets/secura-logo.png" alt="Secura" style={{ height: '34px', objectFit: 'contain' }} />
                        <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />
                        <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700 }}>
                            <ArrowLeft size={15} /> Cases
                        </button>
                        <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />
                        <span style={{ fontFamily: 'monospace', color: '#4f46e5', fontWeight: 700, fontSize: '13px' }}>{caseId}</span>
                        <StatusPill status={caseData.status} />
                    </div>
                </header>
                {/* Blocked content */}
                <div style={{ maxWidth: '600px', margin: '80px auto', padding: '0 24px' }}>
                    <div style={{ background: '#ffffff', border: '1.5px solid #fda4af', borderRadius: '24px', padding: '48px 40px', textAlign: 'center', boxShadow: '0 8px 32px rgba(225,29,72,0.08)' }}>
                        <div style={{ width: '72px', height: '72px', borderRadius: '50%', background: '#fff1f2', border: '1.5px solid #fecdd3', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 24px' }}>
                            <AlertTriangle size={36} style={{ color: '#e11d48' }} />
                        </div>
                        <h2 style={{ fontSize: '22px', fontWeight: 900, color: '#9f1239', margin: '0 0 12px 0', letterSpacing: '-0.01em' }}>Content Blocked by Safety Policy</h2>
                        <p style={{ fontSize: '14px', color: '#be123c', margin: '0 0 28px 0', lineHeight: 1.6 }}>
                            This document triggered a strict safety violation and was blocked from further AI classification to protect downstream systems.
                        </p>
                        {caseData.content_safety_result && (
                            <div style={{ display: 'flex', justifyContent: 'space-around', background: '#fff1f2', border: '1px solid #fecdd3', borderRadius: '14px', padding: '16px' }}>
                                {[
                                    { label: 'Hate', score: caseData.content_safety_result.hate_severity },
                                    { label: 'Self-Harm', score: caseData.content_safety_result.self_harm_severity },
                                    { label: 'Violence', score: caseData.content_safety_result.violence_severity },
                                    { label: 'Sexual', score: caseData.content_safety_result.sexual_severity },
                                ].map(cat => (
                                    <div key={cat.label} style={{ textAlign: 'center' }}>
                                        <p style={{ fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#9f1239', margin: '0 0 4px 0' }}>{cat.label}</p>
                                        <span style={{ fontSize: '16px', fontWeight: 900, color: cat.score >= 4 ? '#dc2626' : '#b91c1c' }}>{cat.score}/7</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={{ minHeight: '100vh', background: '#f8fafc' }}>

            {/* ── Glassmorphism header ── */}
            <header style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)', borderBottom: '1px solid rgba(226,232,240,0.8)', padding: '0 32px', position: 'sticky', top: 0, zIndex: 50 }}>
                <div style={{ maxWidth: '1560px', margin: '0 auto', display: 'flex', alignItems: 'center', height: '64px', gap: '14px' }}>
                    <img src="/assets/secura-logo.png" alt="Secura" style={{ height: '34px', objectFit: 'contain' }} />
                    <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />
                    <button onClick={() => navigate('/')} style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#4f46e5', background: 'none', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 700 }}>
                        <ArrowLeft size={15} /> Cases
                    </button>
                    <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />

                    {/* Case meta */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, flexWrap: 'wrap' }}>
                        <span style={{ fontFamily: 'monospace', color: '#4f46e5', fontWeight: 700, fontSize: '13px' }}>{caseId}</span>
                        {caseData && <StatusPill status={caseData.status} />}
                        {caseData && <CategoryPill category={caseData.classification_category} />}
                        {caseData?.requires_human_review && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#d97706', fontSize: '12px', fontWeight: 700, background: '#fffbeb', border: '1px solid #fcd34d', padding: '3px 10px', borderRadius: '8px' }}>
                                <AlertTriangle size={12} /> Human Review Required
                            </span>
                        )}
                    </div>

                    {/* Actions */}
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <a
                            href={`/reports/${caseId}.html`}
                            download={`${caseId}_report.html`}
                            style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#4f46e5', color: '#fff', padding: '8px 16px', borderRadius: '10px', fontSize: '12px', fontWeight: 700, textDecoration: 'none', boxShadow: '0 4px 12px rgba(79,70,229,0.25)' }}
                        >
                            <Download size={14} /> Report
                        </a>
                        <button onClick={fetchAll} style={{ background: '#ffffff', border: '1.5px solid #e2e8f0', borderRadius: '10px', padding: '8px', cursor: 'pointer', color: '#4f46e5', display: 'flex' }}>
                            <RefreshCw size={15} />
                        </button>
                    </div>
                </div>
            </header>

            {/* Content */}
            <div style={{ maxWidth: '1560px', margin: '0 auto', padding: '28px 32px' }}>

                {/* Safety warning banner (non-blocking) */}
                {caseData?.status === 'NEEDS_REVIEW_SAFETY' && caseData?.content_safety_result && (
                    <div style={{ background: '#fffbeb', border: '1.5px solid #fcd34d', borderRadius: '16px', padding: '14px 20px', marginBottom: '24px', display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <AlertTriangle size={18} style={{ color: '#d97706', flexShrink: 0 }} />
                        <div style={{ flex: 1 }}>
                            <strong style={{ color: '#92400e', fontSize: '14px' }}>Content Safety Warning — </strong>
                            <span style={{ color: '#b45309', fontSize: '13px' }}>This document was flagged for moderate harmful content. Please review carefully.</span>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            {[
                                { label: 'Hate', score: caseData.content_safety_result.hate_severity },
                                { label: 'Self-Harm', score: caseData.content_safety_result.self_harm_severity },
                                { label: 'Violence', score: caseData.content_safety_result.violence_severity },
                                { label: 'Sexual', score: caseData.content_safety_result.sexual_severity },
                            ].map(cat => (
                                <span key={cat.label} style={{
                                    padding: '3px 10px', borderRadius: '8px', fontSize: '10px', fontWeight: 800,
                                    background: cat.score >= 4 ? '#fff1f2' : cat.score >= 2 ? '#fffbeb' : '#f0fdf4',
                                    color: cat.score >= 4 ? '#be123c' : cat.score >= 2 ? '#b45309' : '#15803d',
                                    border: `1px solid ${cat.score >= 4 ? '#fda4af' : cat.score >= 2 ? '#fcd34d' : '#86efac'}`,
                                }}>{cat.label}: {cat.score}</span>
                            ))}
                        </div>
                    </div>
                )}

                {/* ── 2-column layout ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px', alignItems: 'start' }}>

                    {/* ── Left column ── */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

                        {/* Agent Pipeline Panel — full width of left column */}
                        <AgentPipelinePanel caseId={caseId} />

                        {/* Tab switcher */}
                        <div style={{ background: '#f1f5f9', padding: '4px', borderRadius: '14px', display: 'inline-flex', gap: '2px' }}>
                            {tabs.map(tab => (
                                <button
                                    key={tab.key}
                                    onClick={() => setActivePanel(tab.key)}
                                    style={{
                                        display: 'flex', alignItems: 'center', gap: '6px',
                                        padding: '8px 16px', borderRadius: '10px', border: 'none', cursor: 'pointer',
                                        fontSize: '13px', fontWeight: 700,
                                        background: activePanel === tab.key ? '#ffffff' : 'transparent',
                                        color: activePanel === tab.key ? '#0f172a' : '#64748b',
                                        boxShadow: activePanel === tab.key ? '0 1px 6px rgba(0,0,0,0.08)' : 'none',
                                        transition: 'all 0.2s',
                                    }}
                                >
                                    {tab.label}
                                    {tab.count !== undefined && (
                                        <span style={{
                                            background: activePanel === tab.key ? '#eef2ff' : '#e2e8f0',
                                            color: activePanel === tab.key ? '#4f46e5' : '#94a3b8',
                                            padding: '1px 7px', borderRadius: '10px', fontSize: '11px', fontWeight: 800,
                                        }}>{tab.count}</span>
                                    )}
                                </button>
                            ))}
                        </div>

                        {/* Tab content panels */}
                        <div>
                            {activePanel === 'summary' && caseData && <CaseSummaryPanel caseData={caseData} timeline={timeline} />}
                            {activePanel === 'emails' && <EmailChainPanel emails={emails} />}
                            {activePanel === 'documents' && <DocumentsPanel documents={documents} />}
                            {activePanel === 'classification' && <ClassificationPanel caseId={caseId} classification={classification} />}
                        </div>
                    </div>

                    {/* ── Right dark sidebar ── */}
                    <div style={{ position: 'sticky', top: '80px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

                        {/* Extracted fields dark card */}
                        <ExtractedFieldsCard caseData={caseData} classification={classification} dark />

                        {/* Case meta card (dark) */}
                        <div style={{
                            background: '#1e293b', border: '1px solid rgba(255,255,255,0.08)',
                            borderRadius: '20px', padding: '20px',
                        }}>
                            <p style={{ margin: '0 0 16px 0', fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: 'rgba(255,255,255,0.3)' }}>Case Metadata</p>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                {[
                                    { label: 'Case ID', value: caseId },
                                    { label: 'Email Count', value: String(caseData?.email_count ?? 0) },
                                    { label: 'Last Updated', value: caseData?.updated_at ? format(new Date(caseData.updated_at), 'dd MMM HH:mm') : '—' },
                                ].map(f => (
                                    <div key={f.label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: '11px', fontWeight: 600, color: 'rgba(255,255,255,0.35)' }}>{f.label}</span>
                                        <span style={{ fontSize: '12px', fontWeight: 700, color: 'rgba(255,255,255,0.75)', fontFamily: f.label === 'Case ID' ? 'monospace' : 'inherit' }}>{f.value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* PII Report link */}
                        <a
                            href={`/reports/${caseId}.html`}
                            target="_blank"
                            rel="noopener noreferrer"
                            style={{
                                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                background: 'rgba(79,70,229,0.12)', border: '1px solid rgba(79,70,229,0.25)',
                                borderRadius: '16px', padding: '16px 18px',
                                textDecoration: 'none',
                                transition: 'all 0.2s',
                            }}
                            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(79,70,229,0.2)')}
                            onMouseLeave={e => (e.currentTarget.style.background = 'rgba(79,70,229,0.12)')}
                        >
                            <div>
                                <p style={{ margin: '0 0 2px 0', fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#818cf8' }}>PII Report</p>
                                <p style={{ margin: 0, fontSize: '12px', color: '#c7d2fe', fontWeight: 600 }}>View masked content</p>
                            </div>
                            <Download size={16} style={{ color: '#818cf8' }} />
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}
