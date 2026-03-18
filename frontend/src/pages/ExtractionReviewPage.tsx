import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    ChevronLeft,
    FileText, Loader2, ShieldCheck,
    Eye, ExternalLink
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import type { Case, Document as CaseDoc, ClassificationResult } from '../types';
import { EditableFieldsPanel, PanelItem } from '../components/EditableFieldsPanel';


export default function ExtractionReviewPage() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const { instance } = useMsal();
    const apiClient = useMemo(() => createApiClient(instance), [instance]);

    const [caseData, setCaseData] = useState<Case | null>(null);
    const [docs, setDocs] = useState<CaseDoc[]>([]);
    const [classification, setClassification] = useState<ClassificationResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [activeDocId, setActiveDocId] = useState<string | null>(null);

    const fetchAll = async () => {
        if (!caseId) return;
        try {
            const [c, d, cls] = await Promise.all([
                casesApi.getCase(apiClient, caseId),
                casesApi.getCaseDocuments(apiClient, caseId),
                casesApi.getCaseClassification(apiClient, caseId),
            ]);
            setCaseData(c);
            const normalizedDocs = d.documents.map((doc: any) => ({
                ...doc,
                file_name: doc.file_name || doc.filename
            }));
            setDocs(normalizedDocs);
            setClassification(cls.classification);

            if (normalizedDocs.length > 0 && !activeDocId) {
                setActiveDocId(normalizedDocs[0].document_id);
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAll();
    }, [caseId]);

    if (loading || !caseData) {
        return (
            <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-400">
                <Loader2 size={32} className="animate-spin" />
            </div>
        );
    }

    const hitlFields = (classification as any)?.hitl_fields || {};
    const kf = classification?.key_fields;

    const groupedFields: Record<string, PanelItem[]> = {
        'Submission Identity': [
            { label: 'Insured: Name', value: kf?.insured?.name || kf?.name || 'N/A' },
            { label: 'Applicant Name', value: kf?.applicant_name || 'N/A' },
            { label: 'Address', value: kf?.address || kf?.insured?.address || 'N/A' },
            { label: 'Entity Type', value: kf?.entity_type || 'N/A' },
            { label: 'Policy Reference', value: kf?.policy_reference || 'N/A' },
        ],
        'Producer Details': [
            { label: 'Agency', value: kf?.agency || kf?.agent?.agencyName || 'N/A' },
            { label: 'Licensed Producer', value: kf?.licensed_producer || 'N/A' },
            { label: 'Agent: Name', value: kf?.agent?.name || 'N/A' },
            { label: 'Agent: Email', value: kf?.email_address || kf?.agent?.email || 'N/A' },
            { label: 'Agent: Phone', value: kf?.primary_phone || kf?.agent?.phone || 'N/A' },
        ],
        'Policy Details': [
            { label: 'Segment', value: kf?.segment || 'N/A' },
            { label: 'Submission Type', value: kf?.submission_type || 'N/A' },
            { label: 'Effective Date', value: kf?.effective_date || 'N/A' },
            { label: 'IAT Product', value: kf?.iat_product || 'N/A' },
            { label: 'UW / AM', value: kf?.uw_am || 'N/A' },
            { label: 'Primary Rating State', value: kf?.primary_rating_state || 'N/A' },
        ],
        'Risk & Industry': [
            { label: 'NAICS Code', value: kf?.naics_code || 'N/A' },
            { label: 'SIC Code', value: kf?.sic_code || 'N/A' },
            { label: 'Business Description', value: kf?.business_description || 'N/A' },
        ],
        'Risk & Coverages': [
            {
                type: 'table',
                label: 'Coverages',
                headers: ['Coverage', 'Limit', 'Deductible'],
                rows: kf?.coverages?.map((c: any) => ({
                    'Coverage': c.coverage || '',
                    'Limit': c.limit || '',
                    'Deductible': c.deductible || ''
                })) || []
            },
            {
                type: 'table',
                label: 'Exposures',
                headers: ['Exposure Type', 'Value'],
                rows: kf?.exposures?.map((e: any) => ({
                    'Exposure Type': e.exposureType || '',
                    'Value': e.value || ''
                })) || []
            }
        ],
        'Classification': [
            { label: 'Category', value: classification?.classification_category || 'N/A' },
            { label: 'Document Type', value: kf?.document_type || 'Unknown' },
            { label: 'Urgency', value: kf?.urgency || 'Normal' },
        ],
    };

    // Apply HITL overrides
    Object.values(groupedFields).flat().forEach(item => {
        if (item.type !== 'table') {
            const f = item as any;
            if (hitlFields[f.label]) {
                f.original = f.value;
                f.value = hitlFields[f.label];
            }
        }
    });


    const annotatedPdfUrl = activeDocId ? `/api/cases/${caseId}/documents/${activeDocId}/annotated` : '';

    return (
        <div className="h-screen bg-slate-50 flex flex-col overflow-hidden font-sans">
            {/* Header */}
            <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between z-10 shadow-sm">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate('/')} className="p-2 -ml-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
                        <ChevronLeft size={20} />
                    </button>
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <img src="/assets/iat-logo.png" alt="IAT" className="h-5" />
                            <span className="w-1 h-1 bg-slate-300 rounded-full" />
                            <span className="text-[10px] font-black text-indigo-600 uppercase tracking-widest">Extraction Review</span>
                        </div>
                        <h1 className="text-md font-bold text-slate-800 leading-tight">Case: {caseData.subject}</h1>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-full text-[11px] font-bold border border-indigo-100 uppercase tracking-tight">
                        <ShieldCheck size={14} />
                        Human Verification Mode
                    </div>
                </div>
            </header>

            {/* Main Split Layout */}
            <main className="flex-1 flex overflow-hidden">
                {/* LEFT: Pre-rendered Document Viewer */}
                <div className="flex-[6] bg-slate-900 border-r border-slate-800 relative flex flex-col">
                    {/* Document Selector Tabs */}
                    <div className="flex items-center gap-1 p-3 bg-slate-900/50 backdrop-blur-md border-b border-white/5">
                        {docs.map(doc => (
                            <button
                                key={doc.document_id}
                                onClick={() => setActiveDocId(doc.document_id)}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${activeDocId === doc.document_id
                                    ? 'bg-white text-slate-900 shadow-lg'
                                    : 'text-slate-400 hover:text-white hover:bg-white/5'
                                    }`}
                            >
                                <FileText size={14} />
                                <span className="max-w-[150px] truncate">{doc.file_name}</span>
                            </button>
                        ))}
                    </div>

                    <div className="flex-1 relative bg-slate-950 overflow-hidden flex flex-col">
                        {activeDocId ? (
                            <div className="h-full w-full flex flex-col">
                                <div className="p-2 flex items-center justify-between bg-black/20 text-[10px] text-slate-500 font-bold uppercase tracking-widest border-b border-white/5">
                                    <div className="flex items-center gap-2">
                                        <Eye size={12} className="text-indigo-400" />
                                        <span>High-Fidelity Annotated Preview</span>
                                    </div>
                                    <a
                                        href={annotatedPdfUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center gap-1 hover:text-white transition-colors"
                                    >
                                        <ExternalLink size={12} />
                                        Open Full View
                                    </a>
                                </div>
                                <div className="flex-1 h-full w-full">
                                    <object
                                        data={`${annotatedPdfUrl}#toolbar=0&navpanes=0&scrollbar=0`}
                                        type="application/pdf"
                                        className="w-full h-full border-none"
                                    >
                                        <div className="flex flex-col items-center justify-center h-full text-slate-500 gap-4">
                                            <p className="text-sm">Native PDF viewing not supported in your browser.</p>
                                            <a
                                                href={annotatedPdfUrl}
                                                className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-bold hover:bg-indigo-700 transition-colors"
                                            >
                                                Download Annotated PDF
                                            </a>
                                        </div>
                                    </object>
                                </div>
                            </div>
                        ) : (
                            <div className="h-full flex items-center justify-center text-slate-500 flex-col gap-4">
                                <Loader2 size={32} className="animate-spin opacity-20" />
                                <span className="text-sm font-bold opacity-30">Loading Document...</span>
                            </div>
                        )}
                    </div>
                </div>

                {/* RIGHT: Scrollable Fields Panel */}
                <div className="flex-[4] bg-white flex flex-col border-l border-slate-200 shadow-[-10px_0_30px_rgba(0,0,0,0.03)]">
                    <div className="p-6 border-b border-slate-100 bg-slate-50/50">
                        <div className="flex items-center gap-2 mb-2">
                            <div className="p-1 px-2 bg-amber-100 text-amber-700 rounded text-[10px] font-black uppercase tracking-tighter shadow-sm border border-amber-200">
                                Pre-Rendered
                            </div>
                            <h2 className="text-sm font-black text-slate-800 uppercase tracking-tighter">Verification Guide</h2>
                        </div>
                        <p className="text-xs text-slate-500 leading-relaxed font-medium">
                            All extracted fields and confidence scores are highlighted on the document. Verify these values on the left and correct any inaccuracies in the fields below.
                        </p>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar p-6 bg-gradient-to-b from-white to-slate-50/30">
                        <EditableFieldsPanel
                            groupedFields={groupedFields}
                            onSave={async (updates) => {
                                if (!caseId) return;
                                await apiClient.patch(`/cases/${caseId}/fields`, {
                                    fields: updates,
                                    updated_by: 'underwriter_review'
                                });
                                const cls = await casesApi.getCaseClassification(apiClient, caseId);
                                setClassification(cls.classification);
                            }}
                            isReadOnly={false}
                            onSelectField={() => { }} // Simplified: No interaction needed
                            onSelectGroup={() => { }} // Simplified: No interaction needed
                            onFinalSubmit={() => navigate(`/cases/${caseId}`)}
                            finalSubmitLabel="Approve & Proceed"
                        />
                    </div>
                </div>
            </main>
        </div>
    );
}
