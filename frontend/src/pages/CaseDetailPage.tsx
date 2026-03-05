import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { ArrowLeft, AlertTriangle, RefreshCw, Download } from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { StatusBadge } from '../components/StatusBadge';
import { CategoryBadge } from '../components/CategoryBadge';
import { CaseSummaryPanel } from '../components/CaseSummaryPanel';
import { EmailChainPanel } from '../components/EmailChainPanel';
import { DocumentsPanel } from '../components/DocumentsPanel';
import { ClassificationPanel } from '../components/ClassificationPanel';
import type { Case, Email, Document, ClassificationResult, TimelineEvent } from '../types';

type Panel = 'summary' | 'emails' | 'documents' | 'classification';

const getSeverityColor = (score: number) => {
    if (score >= 4) return 'bg-red-100 text-red-800 border-red-200';
    if (score >= 2) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    return 'bg-green-100 text-green-800 border-green-200';
};
const getSeverityLabel = (score: number) => {
    if (score >= 4) return 'High';
    if (score >= 2) return 'Medium';
    return 'Safe';
};

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

    if (loading) return (
        <div style={{ minHeight: '100vh', background: '#F4F6F8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <RefreshCw className="w-8 h-8 animate-spin" style={{ color: '#00467F' }} />
        </div>
    );

    if (error) return (
        <div style={{ minHeight: '100vh', background: '#F4F6F8', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center' }}>
                <p style={{ color: '#b91c1c', fontSize: '16px', fontWeight: 500, marginBottom: '8px' }}>Error loading case</p>
                <p style={{ color: '#8fa1b0', fontSize: '13px', marginBottom: '16px' }}>{error}</p>
                <button onClick={() => navigate('/')} style={{ color: '#00467F', background: 'none', border: 'none', cursor: 'pointer', fontSize: '13px', textDecoration: 'underline' }}>
                    ← Back to cases
                </button>
            </div>
        </div>
    );

    return (
        <div style={{ minHeight: '100vh', background: '#F4F6F8' }}>
            {/* ── Header ── */}
            <header style={{ background: '#ffffff', borderBottom: '1px solid #D1D9E0', padding: '0 32px' }}>
                <div style={{ maxWidth: '1280px', margin: '0 auto', display: 'flex', alignItems: 'center', height: '64px', gap: '16px' }}>
                    <img src="/assets/iat-logo.png" alt="IAT Insurance Group" style={{ height: '38px', width: 'auto', objectFit: 'contain' }} />
                    <div style={{ width: '1px', height: '24px', background: '#D1D9E0' }} />
                    <button
                        onClick={() => navigate('/')}
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00467F', background: 'none', border: 'none', cursor: 'pointer', fontSize: '13px', fontWeight: 500 }}
                    >
                        <ArrowLeft className="w-4 h-4" /> Cases
                    </button>
                    <div style={{ width: '1px', height: '24px', background: '#D1D9E0' }} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1 }}>
                        <span style={{ fontFamily: 'monospace', color: '#00467F', fontWeight: 600, fontSize: '14px' }}>{caseId}</span>
                        {caseData && <StatusBadge status={caseData.status} />}
                        {caseData && <CategoryBadge category={caseData.classification_category} />}
                        {caseData?.requires_human_review && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#f59e0b', fontSize: '12px', fontWeight: 500 }}>
                                <AlertTriangle className="w-3.5 h-3.5" /> Human Review Required
                            </span>
                        )}
                    </div>
                    <button
                        onClick={fetchAll}
                        title="Refresh"
                        style={{ background: 'none', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '7px', cursor: 'pointer', color: '#00467F', display: 'flex' }}
                    >
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>
            </header>

            <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '24px 32px' }}>

                {/* ── AI Summary and Action Bar ── */}
                {caseData?.status === 'BLOCKED_SAFETY' ? (
                    <div style={{ background: '#fef2f2', border: '1px solid #fca5a5', borderRadius: '8px', padding: '32px 24px', textAlign: 'center', margin: '40px auto', maxWidth: '600px', boxShadow: '0 4px 12px rgba(220, 38, 38, 0.1)' }}>
                        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
                            <div style={{ background: '#fee2e2', borderRadius: '50%', padding: '16px' }}>
                                <AlertTriangle className="w-8 h-8 text-red-600" style={{ color: '#dc2626' }} />
                            </div>
                        </div>
                        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#991b1b', margin: '0 0 12px 0' }}>Content Blocked by Safety Policy</h2>
                        <p style={{ fontSize: '15px', color: '#7f1d1d', margin: '0 0 24px 0', lineHeight: '1.6' }}>
                            This document triggered a strict safety violation and was blocked from further AI classification or processing to protect downstream systems.
                        </p>

                        {caseData.content_safety_result && (
                            <div style={{ background: '#ffffff', borderRadius: '6px', padding: '16px', border: '1px solid #fecaca', display: 'flex', justifyContent: 'space-around', alignItems: 'center' }}>
                                <div>
                                    <p style={{ fontSize: '11px', color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 4px 0' }}>Hate</p>
                                    <span style={{ fontSize: '14px', fontWeight: 600, color: caseData.content_safety_result.hate_severity >= 4 ? '#dc2626' : '#991b1b' }}>{caseData.content_safety_result.hate_severity}/7</span>
                                </div>
                                <div style={{ width: '1px', height: '30px', background: '#fecaca' }} />
                                <div>
                                    <p style={{ fontSize: '11px', color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 4px 0' }}>Self-Harm</p>
                                    <span style={{ fontSize: '14px', fontWeight: 600, color: caseData.content_safety_result.self_harm_severity >= 4 ? '#dc2626' : '#991b1b' }}>{caseData.content_safety_result.self_harm_severity}/7</span>
                                </div>
                                <div style={{ width: '1px', height: '30px', background: '#fecaca' }} />
                                <div>
                                    <p style={{ fontSize: '11px', color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 4px 0' }}>Violence</p>
                                    <span style={{ fontSize: '14px', fontWeight: 600, color: caseData.content_safety_result.violence_severity >= 4 ? '#dc2626' : '#991b1b' }}>{caseData.content_safety_result.violence_severity}/7</span>
                                </div>
                                <div style={{ width: '1px', height: '30px', background: '#fecaca' }} />
                                <div>
                                    <p style={{ fontSize: '11px', color: '#991b1b', textTransform: 'uppercase', letterSpacing: '0.05em', margin: '0 0 4px 0' }}>Sexual</p>
                                    <span style={{ fontSize: '14px', fontWeight: 600, color: caseData.content_safety_result.sexual_severity >= 4 ? '#dc2626' : '#991b1b' }}>{caseData.content_safety_result.sexual_severity}/7</span>
                                </div>
                            </div>
                        )}
                    </div>
                ) : (
                    <>
                        {caseData?.status === 'NEEDS_REVIEW_SAFETY' && caseData?.content_safety_result && (
                            <div style={{ background: '#fffbeb', border: '1px solid #fde68a', borderRadius: '8px', padding: '16px 20px', marginBottom: '24px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                    <AlertTriangle className="w-5 h-5" style={{ color: '#d97706' }} />
                                    <strong style={{ color: '#92400e', fontSize: '15px' }}>Content Safety Warning:</strong>
                                    <span style={{ color: '#b45309', fontSize: '14px' }}>This document was flagged for moderate harmful content. Please review carefully.</span>
                                </div>
                                <div style={{ display: 'flex', gap: '12px', paddingLeft: '32px' }}>
                                    {[
                                        { label: 'Hate', score: caseData.content_safety_result.hate_severity },
                                        { label: 'Self-Harm', score: caseData.content_safety_result.self_harm_severity },
                                        { label: 'Violence', score: caseData.content_safety_result.violence_severity },
                                        { label: 'Sexual', score: caseData.content_safety_result.sexual_severity }
                                    ].map(cat => (
                                        <span key={cat.label} className={`px-2.5 py-1 rounded-full text-xs font-medium border ${getSeverityColor(cat.score)}`}>
                                            {cat.label}: {getSeverityLabel(cat.score)}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div style={{ marginBottom: '20px', display: 'flex', gap: '24px', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                            <div style={{ flex: 1, background: '#fff', border: '1px solid #D1D9E0', borderRadius: '8px', padding: '16px 20px', boxShadow: '0 1px 3px rgba(0,38,62,0.04)' }}>
                                <h2 style={{ fontSize: '14px', fontWeight: 700, color: '#00263E', margin: '0 0 8px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>AI Classification Summary</h2>
                                <p style={{ fontSize: '14px', color: '#5a7184', margin: 0, lineHeight: '1.5' }}>
                                    {caseData?.summary || classification?.summary || 'No summary available.'}
                                </p>
                            </div>

                            <a
                                href={`/reports/${caseId}.html`}
                                download={`${caseId}_report.html`}
                                style={{ display: 'flex', flexShrink: 0, alignItems: 'center', gap: '8px', background: '#00467F', color: '#fff', padding: '10px 16px', borderRadius: '6px', fontSize: '13px', fontWeight: 500, textDecoration: 'none', border: 'none', cursor: 'pointer', boxShadow: '0 4px 6px rgba(0, 70, 127, 0.15)', transition: 'transform 0.1s' }}
                                onMouseEnter={(e) => e.currentTarget.style.transform = 'translateY(-1px)'}
                                onMouseLeave={(e) => e.currentTarget.style.transform = 'translateY(0)'}
                            >
                                <Download className="w-4 h-4" /> Download HTML Report
                            </a>
                        </div>

                        {/* PII Masking Report */}
                        <div style={{
                            height: 'calc(100vh - 120px)',
                            width: '100%',
                            background: '#fff',
                            borderRadius: '8px',
                            overflow: 'hidden',
                            border: '1px solid #D1D9E0'
                        }}>
                            <iframe
                                title="PII Masking Report"
                                src={`/reports/${caseId}.html`}
                                style={{ width: '100%', height: '100%', border: 'none' }}
                            />
                        </div>
                    </>
                )}

                {/* Tabs */}
                {caseData?.status !== 'BLOCKED_SAFETY' && (
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', borderBottom: '1px solid #D1D9E0' }}>
                        {tabs.map(tab => (
                            <button
                                key={tab.key}
                                onClick={() => setActivePanel(tab.key)}
                                style={{
                                    background: 'none',
                                    border: 'none',
                                    borderBottom: activePanel === tab.key ? '2px solid #00467F' : '2px solid transparent',
                                    padding: '12px 16px',
                                    fontSize: '14px',
                                    fontWeight: activePanel === tab.key ? 600 : 500,
                                    color: activePanel === tab.key ? '#00263E' : '#5a7184',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px'
                                }}
                            >
                                {tab.label}
                                {tab.count !== undefined && (
                                    <span style={{
                                        background: activePanel === tab.key ? '#e8f0fa' : '#F4F6F8',
                                        color: activePanel === tab.key ? '#00467F' : '#5a7184',
                                        padding: '2px 8px',
                                        borderRadius: '12px',
                                        fontSize: '12px'
                                    }}>
                                        {tab.count}
                                    </span>
                                )}
                            </button>
                        ))}
                    </div>
                )}

                {/* Main Content Area */}
                {caseData?.status !== 'BLOCKED_SAFETY' && (
                    <div>
                        {activePanel === 'summary' && caseData && <CaseSummaryPanel caseData={caseData} timeline={timeline} />}
                        {activePanel === 'emails' && <EmailChainPanel emails={emails} />}
                        {activePanel === 'documents' && <DocumentsPanel documents={documents} />}
                        {activePanel === 'classification' && <ClassificationPanel classification={classification} />}
                    </div>
                )}
            </div>
        </div>
    );
}
