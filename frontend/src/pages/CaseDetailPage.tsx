import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { ArrowLeft, AlertTriangle, RefreshCw } from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { StatusBadge } from '../components/StatusBadge';
import { CategoryBadge } from '../components/CategoryBadge';
import { CaseSummaryPanel } from '../components/CaseSummaryPanel';
import { EmailChainPanel } from '../components/EmailChainPanel';
import { DocumentsPanel } from '../components/DocumentsPanel';
import { ClassificationPanel } from '../components/ClassificationPanel';
import type { Case, Email, Document, ClassificationResult, TimelineEvent } from '../types';

type Panel = 'summary' | 'emails' | 'documents' | 'classification';

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
            </div>
        </div>
    );
}
