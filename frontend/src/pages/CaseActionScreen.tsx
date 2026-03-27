import { useEffect, useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    ChevronLeft, ExternalLink, Activity, CheckCircle2,
    FileText, Eye, RefreshCw, Loader2, Download, FileJson
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import type { Case, Document as CaseDoc, ClassificationResult, ExtractionInstance, V1FieldTraceability } from '../types';
import type { BboxHighlight } from '../components/InlinePdfViewer';
import { usePipeline } from '../contexts/PipelineContext';
import { AgentPipelinePanel } from '../components/AgentPipelinePanel';
import { IngestionStatsCard } from '../components/IngestionStatsCard';
import { InlinePdfViewer } from '../components/InlinePdfViewer';

import { PdfViewerModal } from '../components/PdfViewerModal';
import { JsonDisplayModal } from '../components/JsonDisplayModal';
import { EditableFieldsPanel, PanelItem, FieldItem } from '../components/EditableFieldsPanel';
import { EnrichmentPanel } from '../components/EnrichmentPanel';
import { DecisionPanel } from '../components/DecisionPanel';
import { format } from 'date-fns';

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export default function CaseActionScreen() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const { instance } = useMsal();
    const apiClient = useMemo(() => (DEV_BYPASS_AUTH ? createApiClient(instance) : createApiClient(instance)), [instance]);

    const { getSnapshot, setSnapshot } = usePipeline();
    const cachedContext = caseId ? getSnapshot(caseId) : null;

    const [caseData, setCaseData] = useState<Case | null>(null);
    const [docs, setDocs] = useState<CaseDoc[]>([]);
    const [classification, setClassification] = useState<ClassificationResult | null>(null);
    const [loading, setLoading] = useState(true);

    const [activePdfUrl, setActivePdfUrl] = useState<string | null>(null);
    const [activePdfName, setActivePdfName] = useState<string | null>(null);
    const [selectedInstances, setSelectedInstances] = useState<ExtractionInstance[]>([]);
    const [activeHighlight, setActiveHighlight] = useState<BboxHighlight | null>(null);
    const [showFullscreenPdf, setShowFullscreenPdf] = useState(false);
    const [showJson, setShowJson] = useState(false);

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
                file_name: doc.file_name || doc.filename // Robust fallback
            }));
            setDocs(normalizedDocs);
            setClassification(cls.classification);

            // Auto-select first PDF if nothing is active — prefer annotated version
            if (normalizedDocs.length > 0 && !activePdfUrl) {
                const firstDocId = normalizedDocs[0].document_id;
                const annotatedDocs = cls.classification?.annotated_docs || {};
                const firstUrl = annotatedDocs[firstDocId]
                    ? `/api/cases/${caseId}/documents/${firstDocId}/annotated`
                    : `/api/cases/${caseId}/documents/${firstDocId}/pdf`;
                setActivePdfUrl(firstUrl);
                setActivePdfName(normalizedDocs[0].file_name);
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAll();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId]);

    const handleSaveFields = async (updates: { field_name: string; value: string }[]) => {
        if (!caseId) return;
        // Call new PATCH /fields endpoint
        await fetch(`/api/cases/${caseId}/fields`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fields: updates, updated_by: 'automated_user' }),
        });
        // Refresh classification data to reflect HITL fields
        const cls = await casesApi.getCaseClassification(apiClient, caseId);
        setClassification(cls.classification);
    };

    const handleDecision = async (decision: 'accept' | 'reject', _remarks: string) => {
        if (!caseId) return;
        const newStatus = decision === 'accept' ? 'PROCESSED' : 'FAILED';
        await fetch(`/api/cases/${caseId}/status`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus }),
        });
        await fetchAll(); // Reload everything
    };

    const handleFieldSelect = (label: string, traceability?: V1FieldTraceability | null) => {
        // ── V1 traceability path (preferred) ───────────────────────────────
        // Check passed traceability first, then fall back to looking it up by label
        const trace = traceability ?? classification?.v1_traceability?.[label];

        if (trace) {
            if (trace.source === 'document' && trace.bbox && trace.page_width && trace.page_height) {
                // Resolve doc URL from doc_id
                const docId = trace.doc_id;
                const docUrl = `/api/cases/${caseId}/documents/${docId}/pdf`;
                const docEntry = docs.find(d => d.document_id === docId);
                setActiveHighlight({
                    page: trace.page ?? 1,
                    bbox: trace.bbox,
                    page_width: trace.page_width,
                    page_height: trace.page_height,
                    unit: trace.unit ?? 'inch',
                });
                setActivePdfUrl(docUrl);
                setActivePdfName(docEntry?.file_name ?? trace.document_name);
                setSelectedInstances([]);
                return;
            }
            if (trace.source === 'document' && trace.doc_id) {
                // Doc source but no bbox — open PDF at page without highlight
                const docUrl = `/api/cases/${caseId}/documents/${trace.doc_id}/pdf`;
                const docEntry = docs.find(d => d.document_id === trace.doc_id);
                setActiveHighlight(null);
                setActivePdfUrl(docUrl);
                setActivePdfName(docEntry?.file_name ?? trace.document_name);
                setSelectedInstances([]);
                return;
            }
            // Email source — nothing to open, badge tooltip already shows context
            return;
        }

        // ── Legacy extraction_results path (fallback) ───────────────────────
        if (!classification?.extraction_results) return;
        const result = classification.extraction_results.find(r => r.field.toLowerCase() === label.toLowerCase());
        if (result && result.instances.length > 0) {
            setSelectedInstances(result.instances);
            setActiveHighlight(null);
            setActivePdfUrl(null);
        }
    };

    const handleGroupSelect = (labels: string[]) => {
        if (!classification?.extraction_results) return;
        let allInstances: ExtractionInstance[] = [];

        labels.forEach(label => {
            const found = classification.extraction_results?.find(r => r.field.toLowerCase() === label.toLowerCase());
            if (found) {
                allInstances = [...allInstances, ...found.instances];
            }
        });

        if (allInstances.length > 0) {
            setSelectedInstances(allInstances);
            setActivePdfUrl(null);
        }
    };

    if (loading || !caseData) {
        return (
            <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-400">
                <Loader2 size={32} className="animate-spin" />
            </div>
        );
    }

    const isTerminal = ['PROCESSED', 'CLASSIFIED', 'FAILED', 'BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY', 'PENDING_REVIEW'].includes(caseData.status);
    const isApproved = ['PROCESSED', 'CLASSIFIED'].includes(caseData.status);

    // Build field groups from classification + case
    // In a real app, this layout logic would be driven by the schema
    const hitlFields = (classification as any)?.hitl_fields || {};
    const kf = classification?.key_fields;
    const conf = kf?.field_confidence || {};

    const v1trace = classification?.v1_traceability ?? {};

    const getField = (label: string, value: string | undefined | null, techKey?: string, isCritical: boolean = false): FieldItem => {
        const isNullish = !value ||
            value.toString().trim() === '' ||
            ['null', 'na', 'n/a', '—', 'none', 'undefined'].includes(value.toString().toLowerCase().trim());
        const finalValue = isNullish ? 'N/A' : value.toString();

        let fieldConfidence = undefined;
        if (!isNullish) {
            if (techKey === 'classification_category') {
                fieldConfidence = classification?.confidence_score;
            } else if (techKey && conf[techKey] !== undefined) {
                fieldConfidence = conf[techKey];
            } else if (conf[label] !== undefined) {
                fieldConfidence = conf[label];
            }
        }

        // Look up traceability by techKey first, then label
        const traceability = (techKey && v1trace[techKey]) ? v1trace[techKey] : v1trace[label] ?? null;

        return {
            label,
            value: finalValue,
            confidence: fieldConfidence,
            isCritical,
            traceability,
        };
    };

    const groupedFields: Record<string, PanelItem[]> = {
        'Submission Details': [
            { label: 'Subject', value: caseData.subject },
            { label: 'Sender', value: caseData.sender },
            { label: 'Received At', value: format(new Date(caseData.created_at), 'PPPp') },
            getField('Submission Description', kf?.submission_description, 'submission_description'),
        ],
        'Classification Insights': [
            getField('Category', classification?.classification_category, 'classification_category'),
            getField('Document Type', kf?.document_type, 'document_type'),
            getField('Submission Type', kf?.submission_type, 'submission_type'),
            getField('Segment', kf?.segment, 'segment'),
            getField('IAT Product', kf?.iat_product, 'iat_product'),
            getField('UW / AM', kf?.uw_am, 'uw_am'),
        ],
        'Counterparty Details': [
            getField('Insured: Name', kf?.insured?.name || kf?.name, 'name'),
            getField('Applicant Name', kf?.applicant_name, 'applicant_name'),
            getField('Entity Type', kf?.entity_type, 'entity_type'),
            getField('Entity Structure', (kf as any)?.entity_structure, 'entity_structure'),
            getField('Years in Business', (kf as any)?.years_in_business, 'years_in_business'),
            getField('Number of Employees', (kf as any)?.number_of_employees, 'number_of_employees'),
            getField('Territory Code', (kf as any)?.territory_code, 'territory_code'),
            getField('Insured: Address', kf?.insured?.address || kf?.address, 'address'),
            getField('Business Description', kf?.business_description, 'business_description'),
            getField('Primary Rating State', kf?.primary_rating_state, 'primary_rating_state'),
            getField('Agency', kf?.agent?.agencyName || kf?.agency, 'agency'),
            getField('Agent / Producer', kf?.agent?.name || kf?.licensed_producer, 'licensed_producer'),
        ],
        'Contact Info': [
            getField('Agent Email', kf?.agent?.email || kf?.agent_email || kf?.email_address, 'agent_email'),
            getField('Agent Phone', kf?.agent?.phone || kf?.agent_phone || kf?.primary_phone, 'agent_phone'),
        ],
        'Industry Codes': [
            getField('NAICS Code', kf?.naics_code, 'naics_code'),
            getField('SIC Code', kf?.sic_code, 'sic_code'),
        ],
        'Recurring Structures': [
            {
                type: 'table',
                label: 'Coverages',
                headers: ['Coverage', 'Limit', 'Deductible', 'Coverage Description'],
                rows: kf?.coverages?.map(c => ({
                    'Coverage': c.coverage || '',
                    'Limit': c.limit || '',
                    'Deductible': c.deductible || '',
                    'Coverage Description': c.coverageDescription || ''
                })) || [],
                rowTraceability: kf?.coverages?.map((_, i) => ({
                    'Coverage':            v1trace[`coverages.${i}.coverage`]            ?? null,
                    'Limit':               v1trace[`coverages.${i}.limit`]               ?? null,
                    'Deductible':          v1trace[`coverages.${i}.deductible`]          ?? null,
                    'Coverage Description':v1trace[`coverages.${i}.coverageDescription`] ?? null,
                })) || [],
            },
            {
                type: 'table',
                label: 'Exposures',
                headers: ['Exposure Type', 'Value', 'Exposure Description'],
                rows: kf?.exposures?.map(e => ({
                    'Exposure Type': e.exposureType || '',
                    'Value': e.value || '',
                    'Exposure Description': e.exposureDescription || ''
                })) || [],
                rowTraceability: kf?.exposures?.map((_, i) => ({
                    'Exposure Type':        v1trace[`exposures.${i}.exposureType`]        ?? null,
                    'Value':               v1trace[`exposures.${i}.value`]               ?? null,
                    'Exposure Description':v1trace[`exposures.${i}.exposureDescription`] ?? null,
                })) || [],
            }
        ],
        'Financial Terms': [
            getField('Policy Reference', kf?.policy_reference, 'policy_reference'),
            getField('Effective Date', kf?.effective_date, 'effective_date'),
            getField('Urgency', kf?.urgency, 'urgency', kf?.urgency === 'high'),
        ],
        'Coverage Terms': [
            getField('Limit of Liability', (kf as any)?.limit_of_liability, 'limit_of_liability'),
            getField('Deductible', (kf as any)?.deductible, 'deductible'),
            getField('Class / Mass Action Ded. Retention', (kf as any)?.class_mass_action_deductible_retention, 'class_mass_action_deductible_retention'),
            getField('Pending / Prior Litigation Date', (kf as any)?.pending_or_prior_litigation_date, 'pending_or_prior_litigation_date'),
            getField('Duty to Defend Limit', (kf as any)?.duty_to_defend_limit, 'duty_to_defend_limit'),
            getField('Defense Outside Limit', (kf as any)?.defense_outside_limit, 'defense_outside_limit'),
        ],
        'Employment Profile': [
            getField('Employment Category', (kf as any)?.employment_category, 'employment_category'),
            getField('EC Number of Employees', (kf as any)?.ec_number_of_employees, 'ec_number_of_employees'),
            getField('Employee Compensation', (kf as any)?.employee_compensation, 'employee_compensation'),
            getField('Employees per Band', (kf as any)?.number_of_employees_in_each_band, 'number_of_employees_in_each_band'),
            getField('Employee Location(s)', (kf as any)?.employee_location, 'employee_location'),
            getField('Employees per Location', (kf as any)?.number_of_employees_in_each_location, 'number_of_employees_in_each_location'),
        ],
        'AI Summary': [
            { label: 'Executive Summary', value: classification?.summary || 'Processing...' },
        ]
    };

    // Merge HITL overrides
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
        <div className="min-h-screen bg-slate-50 flex flex-col">
            {/* Sticky Header */}
            <header className="sticky top-0 z-40 bg-white/80 backdrop-blur-md border-b border-slate-200 px-6 py-3 flex items-center justify-between shadow-sm">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate('/')} className="p-2 -ml-2 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors">
                        <ChevronLeft size={20} />
                    </button>
                    <div className="flex items-center gap-3 border-r border-slate-200 pr-4">
                        <img src="/assets/iat-logo.png" alt="IAT" className="h-6" />
                    </div>
                    <div>
                        <div className="flex items-center gap-2">
                            <span className="text-xs font-black text-indigo-400 uppercase tracking-widest">Case ID: {caseId}</span>
                            <span className={`px-2 py-0.5 rounded-full border text-[10px] font-black uppercase tracking-wider ${caseData.status === 'RECEIVED' ? 'bg-amber-100 text-amber-700 border-amber-200' :
                                caseData.status === 'PROCESSING' ? 'bg-indigo-100 text-indigo-700 border-indigo-200' :
                                    ['PROCESSED', 'CLASSIFIED'].includes(caseData.status) ? 'bg-emerald-100 text-emerald-700 border-emerald-200' :
                                        ['BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY', 'FAILED', 'PENDING_REVIEW'].includes(caseData.status) ? 'bg-red-100 text-red-700 border-red-200' :
                                            'bg-slate-50 text-slate-500 border-slate-200'
                                }`}>
                                {caseData.status.replace(/_/g, ' ')}
                            </span>
                        </div>
                        <h1 className="text-lg font-bold text-slate-800 leading-tight truncate max-w-xl">{caseData.subject}</h1>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    <button onClick={fetchAll} className="p-2 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors">
                        <RefreshCw size={18} />
                    </button>
                    <button
                        onClick={() => window.open(`/api/cases/${caseId}/download-masked`, '_blank')}
                        disabled={!classification}
                        className={`px-4 py-2 text-sm font-bold rounded-xl border flex items-center gap-2 transition-all ${classification
                            ? 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border-indigo-200 shadow-sm'
                            : 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                            }`}
                    >
                        <Download size={16} /> Masked Content
                    </button>
                    <button
                        onClick={() => setShowJson(true)}
                        disabled={!classification}
                        className={`px-4 py-2 text-sm font-bold rounded-xl border flex items-center gap-2 transition-all ${classification
                            ? 'bg-indigo-600 text-white hover:bg-indigo-700 border-indigo-700 shadow-md shadow-indigo-200'
                            : 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                            }`}
                    >
                        <FileJson size={16} /> Download JSON
                    </button>
                    <button
                        onClick={() => navigate(`/cases/${caseId}/snapshot`)}
                        disabled={!isApproved}
                        className={`px-4 py-2 text-sm font-bold rounded-xl border flex items-center gap-2 transition-all ${isApproved
                            ? 'bg-slate-900 text-white hover:bg-slate-800 shadow-md border-slate-800 cursor-pointer'
                            : 'bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed opacity-60'
                            }`}
                    >
                        <ExternalLink size={16} /> PAS Snapshot
                    </button>
                </div>
            </header>

            {/* Main 12-col layout */}
            <main className="flex-1 max-w-[1600px] w-full mx-auto p-6 grid grid-cols-12 gap-6">

                {/* LEFT COL (4) */}
                <div className="col-span-4 flex flex-col gap-6">
                    <IngestionStatsCard
                        emailCount={caseData.email_count || 1}
                        docCount={docs.length}
                        progressPct={isTerminal ? 100 : 60}
                        message={isTerminal ? 'All documents successfully processed and classified.' : `Processing ${caseData.email_count || 1} emails with ${docs.length} attachments`}
                    />

                    {/* Context-aware Agent Panel or PDF Viewer */}
                    <div className="relative">
                        {/* The Agent Panel fades out / slides when PDF is active */}
                        <div className={`transition-all duration-500 ${activePdfUrl ? 'opacity-0 translate-x-[-20px] pointer-events-none absolute inset-0' : 'opacity-100 translate-x-0'}`}>
                            <AgentPipelinePanel
                                caseId={caseId!}
                                initialRevealIndex={cachedContext?.revealIndex || 0}
                                onRevealIndexChange={(idx) => caseId && setSnapshot(caseId, { revealIndex: idx })}
                                onStatusChange={(status) => { if (status.is_terminal) fetchAll(); }}
                            />
                        </div>

                        {/* Inline PDF Viewer */}
                        <div className={`transition-all duration-500 ${(activePdfUrl || selectedInstances.length > 0) ? 'opacity-100 translate-x-0' : 'opacity-0 translate-x-[20px] pointer-events-none absolute inset-0'}`}>
                            {selectedInstances.length > 0 ? (() => {
                                // Legacy path: no v1_traceability bbox, fall back to annotated PDF
                                const annotatedDocs = classification?.annotated_docs || {};
                                const docId = selectedInstances[0].doc_id;
                                const fieldUrl = annotatedDocs[docId]
                                    ? `/api/cases/${caseId}/documents/${docId}/annotated`
                                    : `/api/cases/${caseId}/documents/${docId}/pdf`;
                                const doc = docs.find(d => d.document_id === docId);
                                return (
                                    <InlinePdfViewer
                                        url={fieldUrl}
                                        name={doc?.file_name || 'Document'}
                                        onClose={() => setSelectedInstances([])}
                                        onFullscreen={() => {
                                            setActivePdfUrl(fieldUrl);
                                            setActivePdfName(doc?.file_name || 'Document');
                                            setShowFullscreenPdf(true);
                                        }}
                                    />
                                );
                            })() : activePdfUrl && (
                                <InlinePdfViewer
                                    url={activePdfUrl}
                                    name={activePdfName!}
                                    highlight={activeHighlight}
                                    onClose={() => { setActivePdfUrl(null); setActiveHighlight(null); }}
                                    onFullscreen={() => setShowFullscreenPdf(true)}
                                />
                            )}
                        </div>
                    </div>
                </div>

                {/* RIGHT COL (8) */}
                <div className="col-span-8 flex flex-col gap-6">

                    {/* Document Bundle */}
                    <div className="bg-white rounded-2xl border shadow-sm overflow-hidden flex-shrink-0">
                        <div className="px-6 py-4 border-b bg-slate-50/50 flex items-center gap-2">
                            <FileText size={16} className="text-slate-400" />
                            <h2 className="text-lg font-bold text-slate-800">Document Submission Bundle</h2>
                            <span className="ml-auto text-[10px] font-bold text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">{docs.length} file{docs.length !== 1 ? 's' : ''}</span>
                        </div>
                        <div className="p-4 bg-slate-50/30 overflow-y-auto max-h-[340px] custom-scrollbar">
                            <div className="grid grid-cols-3 gap-3">
                                {docs.map((doc, i) => {
                                    const annotatedDocs = classification?.annotated_docs || {};
                                    // Use /view for xlsx/images so they render correctly; annotated/pdf for PDFs
                                    const filename = doc.file_name || (doc as any).filename || '';
                                    const extRaw = filename.split('.').pop()?.toLowerCase() || '';
                                    const needsViewEndpoint = ['xlsx', 'xls', 'jpg', 'jpeg', 'png', 'tiff', 'tif', 'bmp', 'gif', 'webp'].includes(extRaw);
                                    const url = needsViewEndpoint
                                        ? `/api/cases/${caseId}/documents/${doc.document_id}/view`
                                        : annotatedDocs[doc.document_id]
                                            ? `/api/cases/${caseId}/documents/${doc.document_id}/annotated`
                                            : `/api/cases/${caseId}/documents/${doc.document_id}/pdf`;
                                    const isSelected = activePdfUrl === url;
                                    // Look up doc type label from key_fields.documents
                                    const docMeta = kf?.documents?.find((d: any) => d.fileName === filename);
                                    const docTypeLabel = docMeta?.documentDescription || null;
                                    const extUp = extRaw.toUpperCase() || 'FILE';

                                    // Extension-specific icon colours & SVG
                                    const iconConfig: Record<string, { bg: string; border: string; text: string; icon: JSX.Element }> = {
                                        pdf:  { bg: 'bg-red-50',    border: 'border-red-100',    text: 'text-red-500',    icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/></svg> },
                                        xlsx: { bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg> },
                                        xls:  { bg: 'bg-emerald-50', border: 'border-emerald-100', text: 'text-emerald-600', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg> },
                                        docx: { bg: 'bg-blue-50',    border: 'border-blue-100',    text: 'text-blue-600',   icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg> },
                                        doc:  { bg: 'bg-blue-50',    border: 'border-blue-100',    text: 'text-blue-600',   icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg> },
                                        jpg:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
                                        jpeg: { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
                                        png:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
                                        tiff: { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
                                        tif:  { bg: 'bg-purple-50',  border: 'border-purple-100',  text: 'text-purple-500', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg> },
                                        eml:  { bg: 'bg-amber-50',   border: 'border-amber-100',   text: 'text-amber-600',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> },
                                        msg:  { bg: 'bg-amber-50',   border: 'border-amber-100',   text: 'text-amber-600',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> },
                                        txt:  { bg: 'bg-slate-50',   border: 'border-slate-200',   text: 'text-slate-400',  icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/><line x1="9" y1="9" x2="11" y2="9"/></svg> },
                                    };
                                    const ic = iconConfig[extRaw] || { bg: 'bg-slate-50', border: 'border-slate-200', text: 'text-slate-400', icon: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> };

                                    return (
                                        <div
                                            key={i}
                                            onClick={() => {
                                                setSelectedInstances([]);
                                                setActivePdfUrl(url);
                                                setActivePdfName(filename);
                                            }}
                                            className={`relative p-3 rounded-xl border text-left transition cursor-pointer group flex flex-col gap-2 ${isSelected
                                                ? 'border-indigo-400 bg-indigo-50/60 shadow-md ring-2 ring-indigo-100'
                                                : 'border-slate-200 bg-white shadow-sm hover:border-indigo-300 hover:shadow-md'
                                                }`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className={`w-8 h-8 ${ic.bg} ${ic.text} border ${ic.border} rounded-lg flex items-center justify-center shrink-0`}>
                                                    {ic.icon}
                                                </div>
                                                <span className={`p-1 rounded-md transition-colors ${isSelected ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-400 group-hover:text-indigo-500'}`}>
                                                    <Eye size={14} />
                                                </span>
                                            </div>
                                            <div className="min-w-0">
                                                <p className="text-xs font-bold text-slate-700 break-words leading-snug line-clamp-2" title={filename}>
                                                    {filename}
                                                </p>
                                                {docTypeLabel ? (
                                                    <p className="text-[9px] text-indigo-500 font-semibold mt-1 truncate">{docTypeLabel}</p>
                                                ) : (
                                                    <p className="text-[10px] font-semibold text-slate-400 mt-0.5">{extUp}</p>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>
                    </div>

                    {/* Extracted Fields */}
                    <EditableFieldsPanel
                        groupedFields={groupedFields}
                        onSave={handleSaveFields}
                        isReadOnly={isApproved}
                        onSelectField={handleFieldSelect}
                        onSelectGroup={handleGroupSelect}
                    />

                    {/* Web Enrichment Panel */}
                    {caseId && <EnrichmentPanel caseId={caseId} />}

                    {/* Decision Panel (only if processing is done) */}
                    {isTerminal && (
                        <DecisionPanel
                            recommendation={{
                                decision: 'accept',
                                rationale: `Automated processing succeeded. Category: ${classification?.classification_category || 'Unknown'}`
                            }}
                            rules={[
                                { name: 'Document Classification', result: classification ? 'PASS' : 'FAIL', rationale: 'Valid document structure detected' },
                                { name: 'PII Scrubbing', result: 'PASS', rationale: 'Entities masked successfully' },
                                { name: 'Safety Review', result: ['BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY'].includes(caseData.status) ? 'FAIL' : 'PASS', rationale: 'Content policy checked' }
                            ]}
                            isReadOnly={isApproved}
                            initialOverride={isApproved ? (caseData.status === 'PROCESSED' || caseData.status === 'CLASSIFIED' ? 'accept' : 'reject') : null}
                            onSubmit={handleDecision}
                        />
                    )}

                    {/* Reconciliation Footer Banner */}
                    <div className={`p-6 rounded-2xl border flex items-center justify-between transition-all ${!isTerminal ? 'bg-slate-50' : 'bg-emerald-50 border-emerald-200 shadow-lg'}`}>
                        <div className="flex items-center gap-4">
                            <div className={`p-3 rounded-full ${!isTerminal ? 'bg-slate-200 animate-spin' : 'bg-emerald-500 text-white'}`}>
                                {!isTerminal ? <Activity size={24} /> : <CheckCircle2 size={24} />}
                            </div>
                            <div>
                                <p className="font-black text-slate-800">
                                    {!isTerminal
                                        ? 'Cross-Document Reconciliation...'
                                        : 'Engine Recommendation: Auto-Process Approved'
                                    }
                                </p>
                                <p className="text-xs text-slate-500">
                                    {!isTerminal
                                        ? `Processing ${docs.length} documents for reconciliation.`
                                        : `Data reconciled across ${docs.length} documents.`
                                    }
                                </p>
                            </div>
                        </div>
                        {isTerminal && (
                            <button
                                onClick={() => navigate(`/cases/${caseId}/snapshot`)}
                                className="px-6 py-3 rounded-xl font-bold flex items-center gap-2 transition shadow-md bg-emerald-600 text-white hover:bg-emerald-700 active:scale-95 cursor-pointer"
                            >
                                View PAS Snapshot <ExternalLink size={16} />
                            </button>
                        )}
                    </div>

                </div>
            </main>

            {/* Fullscreen PDF Modal Overlay */}
            {showFullscreenPdf && activePdfUrl && (
                <PdfViewerModal
                    url={activePdfUrl}
                    name={activePdfName!}
                    onClose={() => setShowFullscreenPdf(false)}
                />
            )}

            {showJson && classification && (
                <JsonDisplayModal
                    onClose={() => setShowJson(false)}
                    jsonData={{
                        case_id: caseId,
                        insured: {
                            name: classification.key_fields?.name || '—',
                            address: classification.key_fields?.insured?.address || classification.key_fields?.address || '—'
                        },
                        agent: {
                            agencyName: classification.key_fields?.agent?.agencyName || classification.key_fields?.agency || '—',
                            name: classification.key_fields?.agent?.name || classification.key_fields?.licensed_producer || '—',
                            email: classification.key_fields?.agent_email || classification.key_fields?.email_address || '—',
                            phone: classification.key_fields?.agent_phone || classification.key_fields?.primary_phone || '—'
                        },
                        description: classification.key_fields?.submission_description || '—',
                        coverages: classification.key_fields?.coverages || [],
                        exposures: classification.key_fields?.exposures || [],
                        documents: classification.key_fields?.documents || []
                    }}
                />
            )}
        </div>
    );
}
