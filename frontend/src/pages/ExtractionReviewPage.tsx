import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    ChevronLeft,
    FileText, Loader2, ShieldCheck, Info
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import type { Case, Document as CaseDoc, ClassificationResult, ExtractionInstance } from '../types';
import { DocumentAnnotator } from '../components/DocumentAnnotator';
import { EditableFieldsPanel, PanelItem, FieldItem } from '../components/EditableFieldsPanel';

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export default function ExtractionReviewPage() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const { instance } = useMsal();
    const apiClient = useMemo(() => (DEV_BYPASS_AUTH ? createApiClient(instance) : createApiClient(instance)), [instance]);

    const [caseData, setCaseData] = useState<Case | null>(null);
    const [docs, setDocs] = useState<CaseDoc[]>([]);
    const [classification, setClassification] = useState<ClassificationResult | null>(null);
    const [loading, setLoading] = useState(true);

    const [selectedInstances, setSelectedInstances] = useState<ExtractionInstance[]>([]);
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

            // Auto-select first doc for context if nothing is highlighted
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

    const handleFieldSelect = (label: string) => {
        if (!classification?.extraction_results) return;

        const result = classification.extraction_results.find(r => r.field.toLowerCase() === label.toLowerCase());
        if (result && result.instances.length > 0) {
            setSelectedInstances(result.instances);
            setActiveDocId(result.instances[0].doc_id);
        } else {
            console.warn('No extraction coordinates for:', label);
        }
    };

    const handleGroupSelect = (labels: string[]) => {
        if (!classification?.extraction_results) return;
        let allInstances: ExtractionInstance[] = [];

        labels.forEach(label => {
            const found = classification?.extraction_results?.find(r => r.field.toLowerCase() === label.toLowerCase());
            if (found) {
                allInstances = [...allInstances, ...found.instances];
            }
        });

        if (allInstances.length > 0) {
            setSelectedInstances(allInstances);
            setActiveDocId(allInstances[0].doc_id);
        }
    };

    if (loading || !caseData) {
        return (
            <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-400">
                <Loader2 size={32} className="animate-spin" />
            </div>
        );
    }

    // Build field groups
    const hitlFields = (classification as any)?.hitl_fields || {};
    const kf = classification?.key_fields;

    const getFieldConfidence = (label: string) => {
        const res = classification?.extraction_results?.find(r => r.field.toLowerCase() === label.toLowerCase());
        if (!res || res.instances.length === 0) return null;
        return Math.min(...res.instances.map(i => i.confidence));
    };

    const groupedFields: Record<string, PanelItem[]> = {
        'Submission Identity': [
            { label: 'Insured: Name', value: kf?.insured?.name || kf?.name || 'N/A', confidence: getFieldConfidence('Insured: Name') || undefined },
            { label: 'Applicant Name', value: kf?.applicant_name || 'N/A', confidence: getFieldConfidence('Applicant Name') || undefined },
            { label: 'Address', value: kf?.address || kf?.insured?.address || 'N/A', confidence: getFieldConfidence('Address') || undefined },
            { label: 'Entity Type', value: kf?.entity_type || 'N/A', confidence: getFieldConfidence('Entity Type') || undefined },
            { label: 'Policy Reference', value: kf?.policy_reference || 'N/A', confidence: getFieldConfidence('Policy Reference') || undefined },
        ],
        'Producer Details': [
            { label: 'Agency', value: kf?.agency || kf?.agent?.agencyName || 'N/A', confidence: getFieldConfidence('Agency') || undefined },
            { label: 'Licensed Producer', value: kf?.licensed_producer || 'N/A', confidence: getFieldConfidence('Licensed Producer') || undefined },
            { label: 'Agent: Name', value: kf?.agent?.name || 'N/A', confidence: getFieldConfidence('Agent: Name') || undefined },
            { label: 'Agent: Email', value: kf?.email_address || kf?.agent?.email || 'N/A', confidence: getFieldConfidence('Email Address') || undefined },
            { label: 'Agent: Phone', value: kf?.primary_phone || kf?.agent?.phone || 'N/A', confidence: getFieldConfidence('Primary Phone') || undefined },
        ],
        'Policy Details': [
            { label: 'Segment', value: kf?.segment || 'N/A', confidence: getFieldConfidence('Segment') || undefined },
            { label: 'Submission Type', value: kf?.submission_type || 'N/A', confidence: getFieldConfidence('Submission Type') || undefined },
            { label: 'Effective Date', value: kf?.effective_date || 'N/A', confidence: getFieldConfidence('Effective Date') || undefined },
            { label: 'IAT Product', value: kf?.iat_product || 'N/A', confidence: getFieldConfidence('IAT Product') || undefined },
            { label: 'UW / AM', value: kf?.uw_am || 'N/A', confidence: getFieldConfidence('UW / AM') || undefined },
            { label: 'Primary Rating State', value: kf?.primary_rating_state || 'N/A', confidence: getFieldConfidence('Primary Rating State') || undefined },
        ],
        'Risk & Industry': [
            { label: 'NAICS Code', value: kf?.naics_code || 'N/A', confidence: getFieldConfidence('NAICS Code') || undefined },
            { label: 'SIC Code', value: kf?.sic_code || 'N/A', confidence: getFieldConfidence('SIC Code') || undefined },
            { label: 'Business Description', value: kf?.business_description || 'N/A', confidence: getFieldConfidence('Business Description') || undefined },
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
            const f = item as FieldItem;
            if (hitlFields[f.label]) {
                f.original = f.value;
                f.value = hitlFields[f.label];
            }
        }
    });

    return (
        <div className="h-screen bg-slate-50 flex flex-col overflow-hidden">
            {/* Header */}
            <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between z-10">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate('/')} className="p-2 -ml-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
                        <ChevronLeft size={20} />
                    </button>
                    <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                            <img src="/assets/iat-logo.png" alt="IAT" className="h-5" />
                            <span className="w-1 h-1 bg-slate-300 rounded-full" />
                            <span className="text-[10px] font-black text-indigo-500 uppercase tracking-widest">Extraction Review</span>
                        </div>
                        <h1 className="text-md font-bold text-slate-800 leading-tight">Verification Mode: {caseData.subject}</h1>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-lg text-xs font-bold border border-blue-100">
                        <ShieldCheck size={14} />
                        Human-in-the-Loop Active
                    </div>
                </div>
            </header>

            {/* Main Split Layout */}
            <main className="flex-1 flex overflow-hidden">
                {/* LEFT: Full Height PDF Annotator (The "Document" side) */}
                <div className="flex-[6] bg-slate-900 border-r border-slate-800 relative flex flex-col">
                    <div className="absolute inset-0 overflow-auto custom-scrollbar p-6">
                        {selectedInstances.length > 0 ? (
                            <DocumentAnnotator
                                caseId={caseId!}
                                instances={selectedInstances}
                                onClose={() => setSelectedInstances([])}
                                onFullscreen={() => { }} // Disabled or implicit in this view
                            />
                        ) : activeDocId ? (
                            <div className="h-full flex flex-col gap-4">
                                <div className="flex items-center justify-between text-slate-400 px-2">
                                    <div className="flex items-center gap-2 text-xs font-bold">
                                        <FileText size={14} />
                                        <span>Viewing: {docs.find(d => d.document_id === activeDocId)?.file_name}</span>
                                    </div>
                                    <span className="text-[10px] font-mono opacity-50">Click a field on the right to auto-zoom</span>
                                </div>
                                <div className="flex-1 bg-slate-950 rounded-2xl overflow-hidden border border-slate-800 shadow-inner flex items-center justify-center">
                                    <img
                                        src={`/api/cases/${caseId}/documents/${activeDocId}/pages/1/image`}
                                        alt="Document Preview"
                                        className="max-w-[90%] max-h-full object-contain shadow-2xl"
                                    />
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

                {/* RIGHT: Scrollable Fields Panel (The "Extractable Fields" side) */}
                <div className="flex-[4] bg-white flex flex-col border-l border-slate-200 shadow-[-10px_0_30px_rgba(0,0,0,0.02)]">
                    <div className="p-6 border-b border-slate-100 bg-slate-50/30">
                        <div className="flex items-center gap-2 mb-1">
                            <Info size={14} className="text-slate-400" />
                            <h2 className="text-sm font-black text-slate-400 uppercase tracking-tighter">Instructions</h2>
                        </div>
                        <p className="text-xs text-slate-600 leading-relaxed font-medium">
                            Verify the extracted values against the original document. Click any field to highlight its source. Correct any errors before continuing.
                        </p>
                    </div>

                    <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
                        <EditableFieldsPanel
                            groupedFields={groupedFields}
                            onSave={async (updates) => {
                                if (!caseId) return;
                                await apiClient.patch(`/cases/${caseId}/fields`, {
                                    fields: updates,
                                    updated_by: 'underwriter_review'
                                });
                                // Local refresh not strictly needed if we are navigating, but good for robust UI
                                const cls = await casesApi.getCaseClassification(apiClient, caseId);
                                setClassification(cls.classification);
                            }}
                            isReadOnly={false}
                            onSelectField={handleFieldSelect}
                            onSelectGroup={handleGroupSelect}
                            onFinalSubmit={() => navigate(`/cases/${caseId}`)}
                            finalSubmitLabel="Approve & Proceed"
                        />
                    </div>
                </div>
            </main>
        </div>
    );
}
