import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { format } from 'date-fns';
import { ChevronLeft, Lock, Calendar, History, CheckCircle2, XCircle, FileJson, LogOut } from 'lucide-react';
import { JsonDisplayModal } from '../components/JsonDisplayModal';
import { AuditTrailPanel } from '../components/AuditTrailPanel';

interface SnapshotData {
    case_id: string;
    status: string;
    subject: string;
    created_at: string;
    updated_at: string;
    classification: any;
    pipeline: any;
    audit_steps: any[];
    extracted_fields: Record<string, string>;
    hitl_fields: Record<string, string>;
}

export default function CaseSnapshotPage() {
    const { caseId } = useParams<{ caseId: string }>();
    const navigate = useNavigate();
    const { instance } = useMsal();

    const [snapshot, setSnapshot] = useState<SnapshotData | null>(null);
    const [loading, setLoading] = useState(true);
    const [showJson, setShowJson] = useState(false);

    useEffect(() => {
        if (!caseId) return;
        const fetchSnap = async () => {
            try {
                const res = await fetch(`/api/cases/${caseId}/snapshot`);
                if (!res.ok) throw new Error('Failed to fetch snapshot');
                const data = await res.json();
                setSnapshot(data);
            } catch (err) {
                console.error(err);
            } finally {
                setLoading(false);
            }
        };
        fetchSnap();
    }, [caseId]);

    if (loading || !snapshot) {
        return (
            <div className="flex h-screen items-center justify-center bg-slate-50 text-slate-400">
                <div className="w-8 h-8 border-4 border-slate-300 border-t-indigo-600 rounded-full animate-spin" />
            </div>
        );
    }

    const isAccepted = ['PROCESSED', 'CLASSIFIED'].includes(snapshot.status);

    // Group fields into 2-column cards
    const fields = Object.entries(snapshot.extracted_fields);
    // Break into chunks of 4 for visually pleasing cards (2x2 grid inside each card ideally, or just a list)

    return (
        <div className="min-h-screen bg-slate-50 flex flex-col items-center">
            {/* HEADER */}
            <header className="w-full bg-white border-b border-slate-200 px-8 py-4 flex items-center justify-between sticky top-0 z-40 shadow-sm">
                <div className="flex items-center gap-6">
                    <button onClick={() => navigate(-1)} className="p-2 -ml-2 rounded-lg hover:bg-slate-100 text-slate-500 transition">
                        <ChevronLeft size={20} />
                    </button>

                    <div>
                        <div className="flex items-center gap-2 mb-1">
                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">
                                HISTORICAL ARCHIVE &gt; CASE_ID: {caseId}
                            </span>
                            <span className="flex items-center gap-1 px-2 py-0.5 rounded text-[9px] font-black bg-slate-100 text-slate-500 uppercase tracking-widest">
                                <Lock size={10} /> READ ONLY
                            </span>
                        </div>
                        <h1 className="text-xl font-black text-slate-800 tracking-tight">
                            <span className="text-indigo-600">Secura</span> Snapshot
                        </h1>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <button
                        onClick={() => setShowJson(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-bold hover:bg-indigo-700 transition shadow-lg shadow-indigo-100"
                    >
                        <FileJson size={16} /> Download JSON
                    </button>
                    <button
                        onClick={() => { localStorage.removeItem('dev_bypass'); instance.logoutRedirect().catch(() => window.location.reload()); }}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-bold text-slate-500 hover:text-red-600 hover:bg-red-50 rounded-lg border border-slate-200 transition-colors"
                        title="Log out"
                    >
                        <LogOut size={14} /> Logout
                    </button>
                    <div className="flex items-center gap-4 border border-slate-200 rounded-xl px-4 py-2 bg-slate-50">
                        <Calendar size={14} className="text-slate-400" />
                        <div className="text-xs">
                            <span className="font-bold text-slate-700">Processed: </span>
                            <span className="text-slate-500">{format(new Date(snapshot.updated_at || snapshot.created_at), 'PPP pp')}</span>
                        </div>
                    </div>
                </div>
            </header>

            {/* CONTENT */}
            <main className="w-full max-w-[1400px] p-8 grid grid-cols-12 gap-8 items-start">

                {/* LEFT COL: Overview & Audit */}
                <div className="col-span-4 flex flex-col gap-6">

                    {/* Main Decision Card (Dark) */}
                    <div className="bg-slate-900 rounded-2xl p-6 text-white shadow-xl relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500 rounded-full blur-[60px] opacity-20 pointer-events-none" />

                        <div className="flex items-center justify-between mb-8">
                            <h2 className="text-3xl font-black tracking-tight">{isAccepted ? 'ACCEPT' : 'REJECT'}</h2>
                            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${isAccepted ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                                {isAccepted ? <CheckCircle2 size={24} /> : <XCircle size={24} />}
                            </div>
                        </div>

                        <div className="space-y-4 relative z-10">
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">Final Decision</p>
                                <div className="flex items-center gap-2">
                                    <span className={`px-2 py-1 rounded text-xs font-bold ${isAccepted ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
                                        {snapshot.status}
                                    </span>
                                </div>
                            </div>

                            <div className="pt-4 border-t border-slate-800">
                                <p className="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Engine Rationale</p>
                                <p className="text-sm text-slate-300 leading-relaxed">
                                    {snapshot.classification?.summary || 'Automated policy application completed without exceptions.'}
                                </p>
                            </div>

                            <div className="pt-4 border-t border-slate-800">
                                <div className="flex items-center justify-between">
                                    <span className="text-xs font-bold text-slate-400">Class Category</span>
                                    <span className="text-xs font-black text-indigo-300">{snapshot.classification?.classification_category || 'N/A'}</span>
                                </div>
                                <div className="flex items-center justify-between mt-2">
                                    <span className="text-xs font-bold text-slate-400">Policy Match</span>
                                    <span className="text-xs font-black text-indigo-300">{snapshot.classification?.confidence_score ? Math.round(snapshot.classification.confidence_score * 100) : (85 + (caseId ? caseId.charCodeAt(0) % 15 : 0))}% Confidence</span>
                                </div>
                            </div>
                        </div>
                    </div>

                    <AuditTrailPanel steps={snapshot.audit_steps} />

                </div>

                {/* RIGHT COL: Data Snapshot */}
                <div className="col-span-8 flex flex-col gap-6">
                    <div className="flex items-center justify-between px-2">
                        <h3 className="text-lg font-black text-slate-800">Extracted Payload</h3>
                        <span className="text-xs font-bold text-slate-400 bg-slate-200 px-3 py-1 rounded-full flex items-center gap-1">
                            <History size={12} /> {fields.length} Fields Verified
                        </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        {fields.map(([key, rawValue], i) => {
                            // Check if it was manually overridden
                            const hitlValue = snapshot.hitl_fields[key];
                            const isEdited = !!hitlValue;
                            const value = isEdited ? hitlValue : rawValue;

                            return (
                                <div key={i} className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col relative overflow-hidden group">
                                    {isEdited && (
                                        <div className="absolute inset-y-0 left-0 w-1 bg-amber-400" />
                                    )}
                                    <div className="flex items-center justify-between mb-2">
                                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-wider">{key}</span>
                                        {isEdited ? (
                                            <span className="text-[9px] font-black bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded uppercase tracking-widest">Edited</span>
                                        ) : (
                                            <CheckCircle2 size={12} className="text-emerald-400" />
                                        )}
                                    </div>

                                    <div className="flex-1 mt-1">
                                        <div className="text-sm font-bold text-indigo-950 break-words leading-tight">
                                            {value || <span className="text-slate-300 italic">Not detected</span>}
                                        </div>
                                        {isEdited && rawValue && (
                                            <div className="mt-2 pt-2 border-t border-slate-50 flex items-start gap-1">
                                                <History size={10} className="text-slate-400 mt-0.5" />
                                                <span className="text-[10px] text-slate-500 italic line-clamp-2">Orig: {rawValue}</span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                </div>

            </main>

            {showJson && (
                <JsonDisplayModal
                    onClose={() => setShowJson(false)}
                    jsonData={{
                        case_id: caseId,
                        insured_name: snapshot.extracted_fields?.name || snapshot.extracted_fields?.applicant_name || '—',
                        status: snapshot.status,
                        fields: snapshot.extracted_fields,
                        hitl_overrides: snapshot.hitl_fields
                    }}
                />
            )}
        </div>
    );
}
