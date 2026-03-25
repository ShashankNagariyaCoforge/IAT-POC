import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    Inbox, LayoutDashboard, Search,
    Paperclip, ChevronLeft, ChevronRight, Activity, Loader2, BrainCircuit
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import type { Case, Email, Document as CaseDoc } from '../types';
import { CaseThreadList, formatRelativeTime } from '../components/CaseThreadList';
import { EmailChainPanel } from '../components/EmailChainPanel';
import { AgentPipelinePanel } from '../components/AgentPipelinePanel';
import { PdfViewerModal } from '../components/PdfViewerModal';
import { format } from 'date-fns';
import CaseListPage from './CaseListPage';

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';
const POLL_INTERVAL_MS = parseInt(import.meta.env.VITE_DASHBOARD_POLL_INTERVAL_MS || '30000', 10);

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
    const [reprocessKey, setReprocessKey] = useState(0);
    const [skipPii, setSkipPii] = useState(true);

    const fetchCases = useCallback(async () => {
        try {
            const data = await casesApi.listCases(apiClient, { sort_by: 'updated_at', sort_order: 'DESC', page_size: 50 });
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

    const fetchCasesRef = useRef(fetchCases);

    useEffect(() => {
        fetchCasesRef.current = fetchCases;
    }, [fetchCases]);

    const fetchDetailsRef = useRef<() => void>();

    // Auto poll list globally for new cases and active email details
    useEffect(() => {
        if (POLL_INTERVAL_MS <= 0) return;

        const tm = setInterval(() => {
            fetchCasesRef.current();
            if (fetchDetailsRef.current) fetchDetailsRef.current();
        }, POLL_INTERVAL_MS);

        return () => clearInterval(tm);
    }, []);

    useEffect(() => {
        if (!selectedCaseId) {
            fetchDetailsRef.current = undefined;
            return;
        }

        const fetchDetails = async (isBackgroundPoll = false) => {
            if (!isBackgroundPoll) {
                setSelectedDetails(prev => ({ ...prev, loading: true }));
            }
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

        fetchDetailsRef.current = () => fetchDetails(true);
        fetchDetails(false);

        return () => {
            fetchDetailsRef.current = undefined;
        };
    }, [selectedCaseId, apiClient]);

    const selectedCase = cases.find(c => c.case_id === selectedCaseId);

    const handleProcess = async () => {
        if (!selectedCaseId) return;
        setIsProcessing(true);
        try {
            await apiClient.post(`/v2/cases/${selectedCaseId}/process?skip_pii=${skipPii}`);
            navigate(`/cases/${selectedCaseId}`);
            await fetchCases();
            if (fetchDetailsRef.current) fetchDetailsRef.current();
        } catch (error) {
            console.error("Failed to process case:", error);
        } finally {
            setIsProcessing(false);
        }
    };

    const handleResetAndReprocess = async () => {
        if (!selectedCaseId) return;
        setIsProcessing(true);
        setReprocessKey(k => k + 1);
        try {
            await casesApi.resetCase(apiClient, selectedCaseId);
            await handleProcess();
        } catch (error) {
            console.error("Failed to reset and reprocess case:", error);
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
                                    </div>
                                    <div className="text-xs text-slate-500 mt-0.5">
                                        {format(new Date(selectedCase.created_at), 'PPP ')} · {formatRelativeTime(selectedCase.created_at)}
                                    </div>
                                </div>
                            </div>

                            {selectedCase.status === 'RECEIVED' ? (
                                <div className="flex items-center gap-4">
                                    <div className="flex items-center gap-2 px-3 py-2 bg-white border border-slate-200 rounded-xl shadow-sm">
                                        <label className="relative inline-flex items-center cursor-pointer">
                                            <input
                                                type="checkbox"
                                                className="sr-only peer"
                                                checked={!skipPii}
                                                onChange={() => setSkipPii(!skipPii)}
                                            />
                                            <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-indigo-600"></div>
                                            <span className="ml-2 text-xs font-bold text-slate-600 uppercase tracking-tighter">Mask PII</span>
                                        </label>
                                    </div>
                                    <button
                                        onClick={handleProcess}
                                        disabled={isProcessing}
                                        className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl text-sm font-bold shadow-md flex items-center gap-2 transition"
                                    >
                                        {isProcessing ? <><Loader2 size={16} className="animate-spin" /> Queuing...</> : <><Activity size={16} /> Process Case</>}
                                    </button>
                                </div>
                            ) : (
                                <button
                                    onClick={() => navigate(`/cases/${selectedCase.case_id}`)}
                                    className="px-5 py-2.5 bg-white border border-slate-200 hover:bg-slate-50 text-indigo-700 rounded-xl text-sm font-bold shadow-sm flex items-center gap-2 transition"
                                >
                                    View Classified Intelligence <ChevronRight size={16} />
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
                                    {selectedDetails.emails.length > 0 && (
                                        <div className="flex flex-col gap-6">
                                            <EmailChainPanel
                                                emails={selectedDetails.emails}
                                                documents={selectedDetails.documents}
                                                onDocumentClick={(doc) => {
                                                    const url = `/api/cases/${selectedCase.case_id}/documents/${doc.document_id}/pdf`;
                                                    setPdfUrl(url);
                                                    setPdfName(doc.file_name);
                                                }}
                                            />
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
                <div className="w-96 border-l border-slate-200 bg-white shrink-0 flex flex-col h-screen overflow-y-auto custom-scrollbar">
                    <div className="p-6 flex flex-col min-h-full">
                        <div className="flex items-center justify-between mb-6 shrink-0">
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

                        <div className="shrink-0 mb-8">
                            <div className="mb-4 flex items-center justify-between px-1">
                                <span className="text-[10px] font-black uppercase tracking-widest text-slate-400">Data Privacy</span>
                                <label className="relative inline-flex items-center cursor-pointer scale-90 origin-right">
                                    <input
                                        type="checkbox"
                                        className="sr-only peer"
                                        checked={!skipPii}
                                        onChange={() => setSkipPii(!skipPii)}
                                    />
                                    <div className="w-8 h-4 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-indigo-600"></div>
                                    <span className="ml-2 text-[10px] font-bold text-slate-600 uppercase tracking-tighter">Mask PII</span>
                                </label>
                            </div>
                            <AgentPipelinePanel
                                key={`${selectedCase.case_id}-${reprocessKey}`}
                                caseId={selectedCase.case_id}
                                compact
                                skipPii={skipPii}
                            />
                        </div>

                        <div className="mt-auto shrink-0 pt-6">
                            <button
                                onClick={() => navigate(`/cases/${selectedCase.case_id}`)}
                                className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3.5 rounded-xl text-sm transition-all shadow-md flex items-center justify-center gap-2"
                            >
                                <Search size={16} />
                                View Agent Action Screen
                            </button>
                            <button
                                onClick={handleResetAndReprocess}
                                disabled={isProcessing}
                                className={`w-full mt-3 bg-white hover:bg-red-50 border border-slate-200 hover:border-red-200 text-slate-600 hover:text-red-600 font-bold py-3.5 rounded-xl text-sm transition-all flex items-center justify-center gap-2 ${isProcessing ? 'opacity-50 cursor-not-allowed' : ''}`}
                            >
                                <Activity size={15} className={isProcessing ? 'animate-spin' : ''} />
                                {isProcessing ? 'Processing...' : 'Reset & Reprocess'}
                            </button>
                        </div>
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
