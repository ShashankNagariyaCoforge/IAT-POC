import { useState } from 'react';
import { CheckCircle2, XCircle, Zap, Loader2 } from 'lucide-react';

interface Props {
    recommendation: {
        decision: string; // e.g. 'accept' or 'reject'
        rationale: string;
    };
    rules: { name: string; result: 'PASS' | 'FAIL'; rationale: string }[];
    isReadOnly?: boolean;
    initialOverride?: 'accept' | 'reject' | null;
    onSubmit: (decision: 'accept' | 'reject', remarks: string) => Promise<void>;
}

export function DecisionPanel({ recommendation, rules, isReadOnly, initialOverride, onSubmit }: Props) {
    const [decision, setDecision] = useState<'accept' | 'reject' | null>(initialOverride || null);
    const [remarks, setRemarks] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);

    const isNbi = recommendation.decision.toLowerCase() === 'accept';
    const isSelectedNbi = decision === 'accept';
    const isSelectedNty = decision === 'reject';

    const handleSubmit = async () => {
        if (!decision) return;
        setIsSubmitting(true);
        try {
            await onSubmit(decision, remarks);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="bg-white rounded-2xl border shadow-sm overflow-hidden flex flex-col h-full">
            {/* Header */}
            <div className="px-6 py-4 border-b bg-slate-50/50 flex items-center justify-between">
                <h2 className="text-lg font-bold text-slate-800">Decision</h2>
                <div className="flex items-center gap-2">
                    {initialOverride && <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">OVERRIDDEN</span>}
                    <span className={`px-4 py-1.5 rounded-full text-sm font-black uppercase tracking-wider ${isNbi ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' : 'bg-red-100 text-red-700 border border-red-200'
                        }`}>
                        {isNbi ? 'ACCEPT' : 'REJECT'}
                    </span>
                </div>
            </div>

            <div className="p-6 space-y-6 flex-1 overflow-y-auto">
                {/* Rules */}
                {rules.length > 0 && (
                    <div>
                        <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Rules Evaluated</h3>
                        <div className="space-y-2">
                            {rules.map((rule, i) => (
                                <div key={i} className={`flex items-start gap-3 p-3 rounded-lg border ${rule.result === 'PASS' ? 'bg-emerald-50 border-emerald-200' : 'bg-red-50 border-red-200'
                                    }`}>
                                    <span className={`flex-shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center ${rule.result === 'PASS' ? 'bg-emerald-500' : 'bg-red-500'
                                        }`}>
                                        {rule.result === 'PASS' ? <CheckCircle2 size={10} className="text-white" /> : <XCircle size={10} className="text-white" />}
                                    </span>
                                    <div className="flex-1 min-w-0">
                                        <p className={`text-xs font-bold ${rule.result === 'PASS' ? 'text-emerald-700' : 'text-red-700'}`}>
                                            {rule.name}
                                        </p>
                                        <p className="text-[11px] text-slate-500 mt-0.5">{rule.rationale}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* AI Banner */}
                <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${isNbi ? 'bg-emerald-50 border-emerald-100' : 'bg-red-50 border-red-100'
                    }`}>
                    <Zap size={15} className={`flex-shrink-0 ${isNbi ? 'text-emerald-500' : 'text-red-500'}`} />
                    <div className="flex-1 min-w-0">
                        <p className={`text-[10px] font-black uppercase tracking-widest mb-0.5 ${isNbi ? 'text-emerald-600' : 'text-red-400'}`}>
                            Engine Recommendation
                        </p>
                        <p className={`text-sm font-semibold ${isNbi ? 'text-emerald-800' : 'text-red-800'}`}>
                            {recommendation.rationale}
                        </p>
                    </div>
                </div>

                {/* Remarks textarea */}
                <div>
                    <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest block mb-2">Remarks</label>
                    <textarea
                        value={remarks}
                        onChange={(e) => setRemarks(e.target.value)}
                        disabled={isReadOnly}
                        rows={3}
                        placeholder={isReadOnly ? '' : "Add your remarks here..."}
                        className={`w-full px-4 py-3 text-sm rounded-xl border resize-none transition-all focus:outline-none ${isReadOnly
                                ? 'border-slate-200 bg-slate-50 text-slate-600 cursor-default'
                                : 'border-slate-200 bg-slate-50 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 text-slate-700'
                            }`}
                    />
                </div>

                {/* Submit or Locked state */}
                {isReadOnly ? (
                    <div className={`flex items-center gap-3 px-4 py-3 border rounded-xl ${initialOverride === 'accept' ? 'text-emerald-600 bg-emerald-50 border-emerald-200' :
                            initialOverride === 'reject' ? 'text-red-600 bg-red-50 border-red-200' :
                                'text-slate-600 bg-slate-50 border-slate-200'
                        }`}>
                        {initialOverride === 'accept' ? <CheckCircle2 size={16} className="text-emerald-500 flex-shrink-0" /> :
                            initialOverride === 'reject' ? <XCircle size={16} className="text-red-500 flex-shrink-0" /> :
                                <CheckCircle2 size={16} className="text-slate-400 flex-shrink-0" />}
                        <div>
                            <p className="text-xs font-bold">Applied Decision - {
                                initialOverride === 'accept' ? <span className="text-emerald-800">ACCEPT</span> :
                                    initialOverride === 'reject' ? <span className="text-red-800">REJECT</span> : 'AUTO-PROCESSED'
                            }</p>
                            <p className="text-[11px] opacity-80">This case has been reviewed and finalized.</p>
                        </div>
                    </div>
                ) : (
                    <div className="flex items-center justify-between mt-auto shrink-0 pt-4 border-t border-slate-100">
                        <div className="flex items-center gap-4">
                            <label className={`flex items-center gap-2.5 cursor-pointer px-4 py-2.5 rounded-xl border-2 transition-all ${isSelectedNbi ? 'border-emerald-400 bg-emerald-50' : 'border-slate-200 bg-white hover:border-emerald-300'
                                }`}>
                                <input
                                    type="radio"
                                    name="decision"
                                    value="accept"
                                    checked={isSelectedNbi}
                                    onChange={() => setDecision('accept')}
                                    className="accent-emerald-500"
                                />
                                <span className={`text-sm font-bold ${isSelectedNbi ? 'text-emerald-700' : 'text-slate-600'}`}>ACCEPT</span>
                            </label>
                            <label className={`flex items-center gap-2.5 cursor-pointer px-4 py-2.5 rounded-xl border-2 transition-all ${isSelectedNty ? 'border-red-400 bg-red-50' : 'border-slate-200 bg-white hover:border-red-300'
                                }`}>
                                <input
                                    type="radio"
                                    name="decision"
                                    value="reject"
                                    checked={isSelectedNty}
                                    onChange={() => setDecision('reject')}
                                    className="accent-red-500"
                                />
                                <span className={`text-sm font-bold ${isSelectedNty ? 'text-red-700' : 'text-slate-600'}`}>REJECT</span>
                            </label>
                        </div>
                        <button
                            onClick={handleSubmit}
                            disabled={!decision || isSubmitting}
                            className={`px-6 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all ${!decision
                                    ? 'bg-slate-100 text-slate-400 cursor-not-allowed'
                                    : 'bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95 shadow-md'
                                }`}
                        >
                            {isSubmitting ? (
                                <><Loader2 size={15} className="animate-spin" /> Submitting...</>
                            ) : (
                                <><CheckCircle2 size={15} /> Submit Decision</>
                            )}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
