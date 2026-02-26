import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { ArrowLeft, AlertTriangle, RefreshCw } from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { StatusBadge } from '../components/StatusBadge';
import { CategoryBadge } from '../components/CategoryBadge';
import { ConfidenceMeter } from '../components/ConfidenceMeter';
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
        } catch (err: any) {
            setError(err.message || 'Failed to load case.');
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
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
            <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
        </div>
    );

    if (error) return (
        <div className="min-h-screen bg-slate-950 flex items-center justify-center">
            <div className="text-red-400 text-center">
                <p className="text-lg font-medium mb-2">Error loading case</p>
                <p className="text-sm text-slate-400">{error}</p>
                <button onClick={() => navigate('/')} className="mt-4 text-blue-400 hover:underline text-sm">
                    ← Back to cases
                </button>
            </div>
        </div>
    );

    return (
        <div className="min-h-screen bg-slate-950">
            {/* Header */}
            <header className="bg-slate-900 border-b border-slate-800 px-6 py-4">
                <div className="max-w-screen-xl mx-auto flex items-center gap-4">
                    <button
                        onClick={() => navigate('/')}
                        className="text-slate-400 hover:text-white transition-colors flex items-center gap-1.5 text-sm"
                    >
                        <ArrowLeft className="w-4 h-4" /> Cases
                    </button>
                    <div className="h-4 w-px bg-slate-700" />
                    <div className="flex items-center gap-3 flex-1">
                        <span className="font-mono text-blue-400 font-semibold">{caseId}</span>
                        {caseData && <StatusBadge status={caseData.status} />}
                        {caseData && <CategoryBadge category={caseData.classification_category} />}
                        {caseData?.requires_human_review && (
                            <span className="flex items-center gap-1 text-amber-400 text-xs font-medium">
                                <AlertTriangle className="w-3.5 h-3.5" /> Human Review Required
                            </span>
                        )}
                    </div>
                    <button onClick={fetchAll} title="Refresh" className="text-slate-400 hover:text-white">
                        <RefreshCw className="w-4 h-4" />
                    </button>
                </div>
            </header>

            <div className="max-w-screen-xl mx-auto px-6 py-6">
                {/* Quick stats */}
                {caseData && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                        {[
                            { label: 'Sender', value: caseData.sender },
                            { label: 'Emails', value: caseData.email_count.toString() },
                            { label: 'Confidence', value: caseData.confidence_score !== null ? `${Math.round((caseData.confidence_score || 0) * 100)}%` : '—' },
                            { label: 'Routing', value: caseData.routing_recommendation || '—' },
                        ].map(stat => (
                            <div key={stat.label} className="bg-slate-900 border border-slate-800 rounded-xl px-4 py-3">
                                <p className="text-slate-400 text-xs uppercase tracking-wider mb-1">{stat.label}</p>
                                <p className="text-white text-sm font-medium truncate" title={stat.value}>{stat.value}</p>
                            </div>
                        ))}
                    </div>
                )}

                {/* Tab navigation */}
                <div className="flex gap-1 mb-5 bg-slate-900 border border-slate-800 rounded-xl p-1 w-fit">
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            onClick={() => setActivePanel(tab.key)}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5
                ${activePanel === tab.key
                                    ? 'bg-blue-600 text-white'
                                    : 'text-slate-400 hover:text-white'}`}
                        >
                            {tab.label}
                            {tab.count !== undefined && (
                                <span className={`text-xs rounded-full px-1.5 py-0.5
                  ${activePanel === tab.key ? 'bg-blue-500' : 'bg-slate-700 text-slate-400'}`}>
                                    {tab.count}
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {/* Panel content */}
                {caseData && activePanel === 'summary' && (
                    <CaseSummaryPanel caseData={caseData} timeline={timeline} />
                )}
                {activePanel === 'emails' && <EmailChainPanel emails={emails} />}
                {activePanel === 'documents' && <DocumentsPanel documents={documents} />}
                {activePanel === 'classification' && (
                    <ClassificationPanel classification={classification} />
                )}
            </div>
        </div>
    );
}
