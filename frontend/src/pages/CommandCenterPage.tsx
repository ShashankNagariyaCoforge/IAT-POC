import { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    Inbox, LayoutDashboard, Search,
    Paperclip, ChevronLeft, ChevronRight, Activity, Loader2, BrainCircuit
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import type { Case, Email, Document as CaseDoc } from '../types';
import { CaseThreadList, formatRelativeTime } from '../components/CaseThreadList';
import { AgentPipelinePanel } from '../components/AgentPipelinePanel';
import { PdfViewerModal } from '../components/PdfViewerModal';
import { format } from 'date-fns';
import CaseListPage from './CaseListPage';

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export default function CommandCenterPage() {
    const { instance } = useMsal();
    const navigate = useNavigate();
    const apiClient = useMemo(() => (DEV_BYPASS_AUTH ? createApiClient(instance) : createApiClient(instance)), [instance]);

    const [activeTab, setActiveTab] = useState<'inbox' | 'dashboard'>('inbox');
    const [cases, setCases] = useState<Case[]>([]);
    const [selectedCaseId, setSelectedCaseId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    // Details for selected case in inbox
    const [selectedDetails, setSelectedDetails] = useState<{
        emails: Email[];
        documents: CaseDoc[];
        loading: boolean;
    }>({ emails: [], documents: [], loading: false });

    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [pdfName, setPdfName] = useState<string>('');
    const [isProcessing, setIsProcessing] = useState(false);

    const fetchCases = useCallback(async () => {
        try {
            const data = await casesApi.listCases(apiClient, { sort_by: 'created_at', sort_order: 'DESC', page_size: 50 });
            setCases(data.cases);
            if (!selectedCaseId && data.cases.length > 0) {
                setSelectedCaseId(data.cases[0].case_id);
            }
        } finally {
            setLoading(false);
        }
    }, [apiClient, selectedCaseId]);

    useEffect(() => {
        fetchCases();
    }, [fetchCases]);

    // Auto poll list if there are cases actively processing
    useEffect(() => {
        const hasActive = cases.some(c => c.status === 'PROCESSING');
        if (!hasActive) return;
        const tm = setInterval(fetchCases, 5000);
        return () => clearInterval(tm);
    }, [cases, fetchCases]);

    useEffect(() => {
        if (!selectedCaseId) return;
        const fetchDetails = async () => {
            setSelectedDetails(prev => ({ ...prev, loading: true }));
            try {
                const [emData, docData] = await Promise.all([
                    casesApi.getCaseEmails(apiClient, selectedCaseId),
                    casesApi.getCaseDocuments(apiClient, selectedCaseId),
                ]);
                setSelectedDetails({ emails: emData.emails, documents: docData.documents, loading: false });
            } catch {
                setSelectedDetails({ emails: [], documents: [], loading: false });
            }
        };
        fetchDetails();
    }, [selectedCaseId, apiClient]);

    const selectedCase = cases.find(c => c.case_id === selectedCaseId);

    const handleProcess = async () => {
        if (!selectedCaseId) return;
        setIsProcessing(true);
        try {
            await fetch('/api/cases/sync', { method: 'POST' }); // trigger sync
            await fetchCases();
        } finally {
            setIsProcessing(false);
        }
    };

    const navPrevNext = (dir: -1 | 1) => {
        if (!selectedCaseId) return;
        const idx = cases.findIndex(c => c.case_id === selectedCaseId);
        if (idx < 0) return;
        const newIdx = idx + dir;
        if (newIdx >= 0 && newIdx < cases.length) {
            setSelectedCaseId(cases[newIdx].case_id);
        }
    };

    const showAI = selectedCase?.status && !['RECEIVED'].includes(selectedCase.status);

    if (activeTab === 'dashboard') {
        return (
            <div className="flex flex-col h-screen bg-slate-50">
                <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between shrink-0">
                    <div className="flex items-center gap-3">
                        <img src="/assets/iat-logo.png" alt="IAT" className="h-6" />
                        <h1 className="text-xl font-black text-slate-900 tracking-tight">Command Center</h1>
                    </div>
                    <div className="flex bg-slate-100 p-1 rounded-lg">
                        <button onClick={() => setActiveTab('inbox')} className="px-4 py-1.5 text-sm font-bold rounded-md text-slate-500 hover:text-slate-900">Inbox</button>
                        <button className="px-4 py-1.5 text-sm font-bold rounded-md bg-white text-indigo-700 shadow-sm border border-slate-200/60">Dashboard</button>
                    </div>
                </header>
                <div className="flex-1 overflow-auto">
                    {/* We embed the existing CaseListPage here but without its own navbar if possible, or just render it directly for now */}
                    <CaseListPage />
                </div>
            </div>
        );
    }

    // --- INBOX TAB ---
    return (
        <div className="flex h-screen bg-white overflow-hidden text-slate-900">
            {/* LEFT: THREAD LIST (w-80) */}
            <div className="w-80 flex flex-col border-r border-slate-200 bg-slate-50/50 shrink-0">
                <div className="p-4 border-b border-slate-200 bg-white flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <img src="/assets/iat-logo.png" alt="IAT" className="h-5" />
                            <span className="font-black text-lg tracking-tight">Command Center</span>
                        </div>
                    </div>
                    <div className="flex bg-slate-100 p-1 rounded-lg">
                        <button className="flex-1 py-1.5 text-sm font-bold rounded-md bg-white text-indigo-700 shadow-sm border border-slate-200/60 flex items-center justify-center gap-2">
                            <Inbox size={14} /> Inbox
                        </button>
                        <button onClick={() => setActiveTab('dashboard')} className="flex-1 py-1.5 text-sm font-bold rounded-md text-slate-500 hover:text-slate-900 flex items-center justify-center gap-2">
                            <LayoutDashboard size={14} /> Dashboard
                        </button>
                    </div>
                </div>

                <CaseThreadList
                    cases={cases}
                    selectedId={selectedCaseId}
                    onSelect={setSelectedCaseId}
                    isLoading={loading}
                />
            </div>

            {/* CENTER: EMAIL DETAIL */}
            <div className="flex-1 flex flex-col min-w-0 bg-white">
                {selectedCase ? (
                    <>
                        <div className="px-8 py-6 border-b border-slate-100 flex items-center justify-between shrink-0 bg-white">
                            <div className="flex flex-col gap-1 min-w-0">
                                <span className="text-[10px] font-black text-indigo-400 uppercase tracking-widest">
                                    CASE ID: {selectedCase.case_id}
                                </span>
                                <h2 className="text-2xl font-black text-slate-800 truncate pr-4">
                                    {selectedCase.subject}
                                </h2>
                            </div>
                            <div className="flex items-center gap-3 shrink-0">
                                <button onClick={() => navPrevNext(-1)} className="p-2 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-400"><ChevronLeft size={18} /></button>
                                <button onClick={() => navPrevNext(1)} className="p-2 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-400"><ChevronRight size={18} /></button>
                            </div>
                        </div>

                        <div className="flex items-center justify-between px-8 py-4 bg-slate-50/50 border-b border-slate-100 shrink-0">
                            <div className="flex items-center gap-3">
                                <div className="w-10 h-10 bg-indigo-100 text-indigo-700 font-bold rounded-full flex items-center justify-center text-sm">
                                    {selectedCase.sender.substring(0, 2).toUpperCase()}
                                </div>
                                <div>
                                    <div className="text-sm">
                                        <span className="font-bold text-slate-900">{selectedCase.sender}</span>
                                        <span className="text-slate-400 ml-2">→ internal@iat.com</span>
                                    </div>
                                    <div className="text-xs text-slate-500 mt-0.5">
                                        {format(new Date(selectedCase.created_at), 'PPP ')} · {formatRelativeTime(selectedCase.created_at)}
                                    </div>
                                </div>
                            </div>

                            {selectedCase.status === 'RECEIVED' ? (
                                <button
                                    onClick={handleProcess}
                                    disabled={isProcessing}
                                    className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md flex items-center gap-2 transition"
                                >
                                    {isProcessing ? <><Loader2 size={16} className="animate-spin" /> Queuing...</> : <><Activity size={16} /> Process Case</>}
                                </button>
                            ) : (
                                <button
                                    onClick={() => navigate(`/cases/${selectedCase.case_id}`)}
                                    className="px-5 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-indigo-700 rounded-xl text-sm font-bold shadow-sm flex items-center gap-2 transition"
                                >
                                    View Agent Action Screen <ChevronRight size={16} />
                                </button>
                            )}
                        </div>

                        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar">
                            {selectedDetails.loading ? (
                                <div className="flex items-center justify-center h-full text-slate-400">
                                    <Loader2 size={24} className="animate-spin" />
                                </div>
                            ) : (
                                <div className="space-y-8 max-w-3xl">
                                    {selectedDetails.emails.length > 0 && selectedDetails.emails[0] && (
                                        <div className="flex flex-col gap-6">
                                            {(selectedDetails.emails[0].body || selectedDetails.emails[0].body_preview || '(No email content available)').split(/_+/g).map((threadPart: string, i: number) => (
                                                <div key={i} className={`p-5 rounded-2xl text-[14px] leading-relaxed font-medium whitespace-pre-wrap ${i === 0 ? 'bg-white border border-slate-200 text-slate-800 shadow-sm' : 'bg-slate-50 text-slate-600 border border-slate-100'}`}>
                                                    {threadPart.trim()}
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    {selectedDetails.documents.length > 0 && (
                                        <div className="pt-6 border-t border-slate-100">
                                            <h4 className="font-bold text-slate-900 mb-4 flex items-center gap-2">
                                                <Paperclip size={16} /> Attached Documents ({selectedDetails.documents.length})
                                            </h4>
                                            <div className="grid grid-cols-2 gap-4">
                                                {selectedDetails.documents.map((doc, idx) => {
                                                    const url = `/api/cases/${selectedCase.case_id}/documents/${doc.document_id}/pdf`;
                                                    return (
                                                        <div
                                                            key={idx}
                                                            onClick={() => { setPdfUrl(url); setPdfName(doc.file_name); }}
                                                            className="flex items-center p-3 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:shadow-md cursor-pointer transition-all group"
                                                        >
                                                            <div className="w-8 h-8 bg-red-50 border border-red-100 rounded flex items-center justify-center text-[10px] font-black tracking-wider text-red-500 mr-3">
                                                                PDF
                                                            </div>
                                                            <span className="text-sm font-semibold text-slate-700 line-clamp-1 flex-1 group-hover:text-indigo-700 transition-colors">
                                                                {doc.file_name}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                ) : (
                    <div className="flex items-center justify-center h-full text-slate-400">
                        Select a case to view details
                    </div>
                )}
            </div>

            {/* RIGHT: AI ASSISTANT (w-96) */}
            {showAI && selectedCase && (
                <div className="w-96 border-l border-slate-200 bg-white shrink-0 flex flex-col items-stretch">
                    <div className="p-6">
                        <div className="flex items-center justify-between mb-6">
                            <div className="flex items-center gap-2">
                                <div className="p-2 bg-indigo-50 rounded-lg text-indigo-600">
                                    <BrainCircuit size={20} />
                                </div>
                                <h2 className="font-bold text-lg">AI Assistant</h2>
                            </div>
                            <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-[10px] font-black uppercase tracking-wider bg-indigo-50 text-indigo-600">
                                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                                Live
                            </div>
                        </div>

                        <AgentPipelinePanel
                            caseId={selectedCase.case_id}
                            compact
                        />

                        <button
                            onClick={() => navigate(`/cases/${selectedCase.case_id}`)}
                            className="w-full mt-6 bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3.5 rounded-xl text-sm transition-all shadow-md flex items-center justify-center gap-2"
                        >
                            <Search size={16} />
                            View Action Screen
                        </button>
                        <button
                            className="w-full mt-3 bg-white hover:bg-red-50 border border-slate-200 hover:border-red-200 text-slate-600 hover:text-red-600 font-bold py-3.5 rounded-xl text-sm transition-all flex items-center justify-center gap-2"
                        >
                            <Activity size={15} />
                            Reset & Reprocess
                        </button>
                    </div>
                </div>
            )}

            {pdfUrl && (
                <PdfViewerModal
                    url={pdfUrl}
                    name={pdfName}
                    onClose={() => setPdfUrl(null)}
                />
            )}
        </div>
    );
}
