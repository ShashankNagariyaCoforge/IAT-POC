import { useState } from 'react';
import { X, Copy, CheckCircle2, Download } from 'lucide-react';

interface Props {
    jsonData: any;
    onClose: () => void;
}

export function JsonDisplayModal({ jsonData, onClose }: Props) {
    const [copied, setCopied] = useState(false);

    const handleCopy = () => {
        navigator.clipboard.writeText(JSON.stringify(jsonData, null, 2));
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div
            className="fixed inset-0 z-[1000] bg-slate-900/80 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={e => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div className="bg-white rounded-3xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden border border-slate-200">
                {/* Header */}
                <div className="px-8 py-5 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
                    <div>
                        <h3 className="text-xl font-black text-slate-800 tracking-tight">Generated Submission JSON</h3>
                        <p className="text-xs font-bold text-slate-500 uppercase tracking-widest mt-1">Ready for downstream integration</p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => {
                                const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' });
                                const url = URL.createObjectURL(blob);
                                const a = document.createElement('a');
                                a.href = url;
                                a.download = `submission_data.json`;
                                a.click();
                                URL.revokeObjectURL(url);
                            }}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all border bg-white text-slate-700 border-slate-200 hover:bg-slate-50 active:scale-95 shadow-sm"
                        >
                            <Download size={16} />
                            Download JSON
                        </button>
                        <button
                            onClick={handleCopy}
                            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all border ${copied
                                ? 'bg-emerald-50 text-emerald-600 border-emerald-200'
                                : 'bg-indigo-600 text-white border-indigo-700 hover:bg-indigo-700 active:scale-95 shadow-lg shadow-indigo-200'
                                }`}
                        >
                            {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                            {copied ? 'Copied!' : 'Copy JSON'}
                        </button>
                        <button
                            onClick={onClose}
                            className="p-2 rounded-xl text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
                        >
                            <X size={20} />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto p-8 bg-slate-950">
                    <pre className="text-indigo-300 font-mono text-sm leading-relaxed">
                        {JSON.stringify(jsonData, null, 2)}
                    </pre>
                </div>

                {/* Footer */}
                <div className="px-8 py-4 border-t border-slate-100 flex items-center justify-between bg-white text-[10px] font-black uppercase tracking-widest text-slate-400">
                    <span>Format: IAT Standard Extraction</span>
                    <span className="flex items-center gap-4">
                        <span>Press ESC to close</span>
                        <span className="text-slate-300">•</span>
                        <span className="text-indigo-600">Confidential</span>
                    </span>
                </div>
            </div>
        </div>
    );
}
