import { useState } from 'react';
import { History, Loader2, CheckCircle2, AlertTriangle, Lock, ArrowRight, FileText, Mail, X } from 'lucide-react';
import type { V1FieldTraceability } from '../types';

export interface FieldItem {
    label: string;
    id?: string; // Optional: Unique ID or backend key for coordinate matching
    value: string;
    original?: string;
    confidence?: number;
    isCritical?: boolean;
    error?: string;
    type?: 'field' | 'table_cell';
    traceability?: V1FieldTraceability | null;
    tooltip?: string; // hover tooltip shown over the field value
}

export interface TableItem {
    type: 'table';
    label: string;
    headers: string[];
    rows: Record<string, string>[];
    /** Per-cell traceability: rowTraceability[rowIndex][header] */
    rowTraceability?: Array<Record<string, V1FieldTraceability | null>>;
}

export type PanelItem = FieldItem | TableItem;

interface Props {
    groupedFields: Record<string, PanelItem[]>;
    onSave: (fields: { field_name: string; value: string }[]) => Promise<void>;
    isReadOnly?: boolean;
    onSelectField?: (label: string, traceability?: V1FieldTraceability | null) => void;
    onSelectGroup?: (labels: string[]) => void;
    onFinalSubmit?: () => void;
    finalSubmitLabel?: string;
}

export function EditableFieldsPanel({
    groupedFields,
    onSave,
    isReadOnly = false,
    onSelectField,
    onSelectGroup,
    onFinalSubmit,
    finalSubmitLabel
}: Props) {
    const [editedFields, setEditedFields] = useState<Record<string, string>>({});
    const [expandedCats, setExpandedCats] = useState<Record<string, boolean>>({});
    const [showOriginal, setShowOriginal] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);

    // Initialize all categories as expanded
    if (Object.keys(expandedCats).length === 0 && Object.keys(groupedFields).length > 0) {
        const initCats: Record<string, boolean> = {};
        Object.keys(groupedFields).forEach(k => initCats[k] = true);
        setExpandedCats(initCats);
    }

    const handleFieldChange = (label: string, val: string) => {
        if (isReadOnly) return;
        setEditedFields(prev => ({ ...prev, [label]: val }));
    };

    const handleSave = async () => {
        setIsSaving(true);
        const updates = Object.entries(editedFields).map(([k, v]) => ({ field_name: k, value: v }));
        try {
            await onSave(updates);
            setEditedFields({});
            setShowOriginal(null);
        } finally {
            setIsSaving(false);
        }
    };

    const handleFinalSubmit = async () => {
        setIsSaving(true);
        try {
            if (hasEdits) {
                const updates = Object.entries(editedFields).map(([k, v]) => ({ field_name: k, value: v }));
                await onSave(updates);
                setEditedFields({});
            }
            onFinalSubmit?.();
        } finally {
            setIsSaving(false);
        }
    };

    const hasEdits = Object.keys(editedFields).length > 0;

    return (
        <div className="bg-white rounded-2xl border shadow-sm overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b bg-slate-50/50 flex items-center justify-between shrink-0">
                <h2 className="text-lg font-bold text-slate-800">Extracted Entities</h2>
                {isReadOnly ? (
                    <span className="text-xs font-semibold text-slate-500 bg-slate-100 px-3 py-1 rounded-full flex items-center gap-1">
                        <Lock size={10} /> Read-only
                    </span>
                ) : hasEdits && (
                    <span className="text-xs font-semibold text-amber-600 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                        {Object.keys(editedFields).length} field(s) modified
                    </span>
                )}
            </div>

            <div className="p-4 flex-1 overflow-y-auto">
                <div className="grid grid-cols-2 gap-4">
                    {Object.entries(groupedFields).map(([category, fields]) => (
                        <div key={category} className="bg-slate-50 rounded-xl border border-slate-200 overflow-hidden flex flex-col">
                            <div
                                className="px-4 py-3 bg-gradient-to-r from-indigo-50 to-slate-50 border-b border-slate-200 cursor-pointer flex items-center justify-between transition-colors hover:bg-slate-100"
                                onClick={() => setExpandedCats(p => ({ ...p, [category]: !p[category] }))}
                            >
                                <div>
                                    <h4 className="text-xs font-black text-slate-700 uppercase tracking-wider">{category}</h4>
                                    <p className="text-[10px] text-slate-500 mt-0.5">{fields.length} fields</p>
                                </div>
                            </div>

                            {expandedCats[category] && (
                                <div className="p-4 space-y-4">
                                    {fields.map((item, idx) => {
                                        if (item.type === 'table') {
                                            return (
                                                <div key={idx} className="space-y-2">
                                                    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                                                        {item.label}
                                                    </label>
                                                    <div className="overflow-x-auto rounded-lg border border-slate-200">
                                                        <table className="w-full text-left text-xs">
                                                            <thead className="bg-slate-100 border-b border-slate-200">
                                                                <tr>
                                                                    {item.headers.map(h => (
                                                                        <th key={h} className="px-3 py-2 font-black text-slate-600 uppercase tracking-tighter">{h}</th>
                                                                    ))}
                                                                </tr>
                                                            </thead>
                                                            <tbody className="bg-white">
                                                                {item.rows.map((row, rIdx) => (
                                                                    <tr key={rIdx} className="border-b border-slate-100">
                                                                        {item.headers.map(h => {
                                                                            const cellVal = row[h] || row[h.toLowerCase()] || row[h.replace(/ /g, '_').toLowerCase()] || '—';
                                                                            const cellTrace = item.rowTraceability?.[rIdx]?.[h] ?? null;
                                                                            const isDoc = cellTrace?.source === 'document';
                                                                            const isEmail = cellTrace?.source === 'email';
                                                                            const isClickable = !!cellTrace && (isDoc || isEmail);
                                                                            return (
                                                                                <td
                                                                                    key={h}
                                                                                    className={`px-3 py-2 text-slate-700 font-semibold group/cell relative ${isClickable ? 'cursor-pointer hover:bg-indigo-50/70' : ''}`}
                                                                                    onClick={() => {
                                                                                        if (isClickable) {
                                                                                            onSelectField?.(`${item.label} [${rIdx + 1}]: ${h}`, cellTrace);
                                                                                        }
                                                                                    }}
                                                                                    title={isEmail && cellTrace ? cellTrace.raw_text : undefined}
                                                                                >
                                                                                    <span className="flex items-center gap-1.5">
                                                                                        {cellVal}
                                                                                        {isDoc && (
                                                                                            <FileText size={8} className="text-indigo-400 shrink-0 opacity-0 group-hover/cell:opacity-100 transition-opacity" />
                                                                                        )}
                                                                                        {isEmail && (
                                                                                            <Mail size={8} className="text-sky-400 shrink-0 opacity-0 group-hover/cell:opacity-100 transition-opacity" />
                                                                                        )}
                                                                                    </span>
                                                                                </td>
                                                                            );
                                                                        })}
                                                                    </tr>
                                                                ))}
                                                            </tbody>
                                                        </table>
                                                    </div>
                                                </div>
                                            );
                                        }

                                        const f = item as FieldItem;
                                        const currentVal = editedFields[f.label] !== undefined ? editedFields[f.label] : f.value;
                                        const isEdited = editedFields[f.label] !== undefined || (f.original && f.original !== f.value);
                                        const isFocus = showOriginal === f.label;

                                        return (
                                            <div
                                                key={f.label}
                                                className={`space-y-1.5 p-2 rounded-lg transition-colors hover:bg-white border border-transparent ${onSelectField ? 'hover:border-indigo-200 hover:shadow-sm' : ''}`}
                                                onClick={() => onSelectField?.(f.id || f.label, f.traceability)}
                                            >
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2 flex-wrap">
                                                        <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wide cursor-pointer">
                                                            {f.label} {f.isCritical && <span className="text-red-500 ml-0.5">*</span>}
                                                        </label>

                                                        {/* Source badge — DOC or EMAIL */}
                                                        {f.traceability && (
                                                            f.traceability.source === 'document' ? (
                                                                <span
                                                                    title={
                                                                        f.traceability.source === 'document' && f.traceability.document_name
                                                                            ? `${f.traceability.document_name}${f.traceability.page ? ` • page ${f.traceability.page}` : ''}`
                                                                            : 'Found in document'
                                                                    }
                                                                    className="inline-flex items-center gap-0.5 text-[8px] font-black px-1.5 py-0.5 rounded border bg-indigo-50 text-indigo-600 border-indigo-100 uppercase tracking-tight cursor-pointer select-none"
                                                                >
                                                                    <FileText size={8} />
                                                                    DOC
                                                                </span>
                                                            ) : (
                                                                <span
                                                                    title={f.traceability.raw_text || 'Found in email'}
                                                                    className="inline-flex items-center gap-0.5 text-[8px] font-black px-1.5 py-0.5 rounded border bg-sky-50 text-sky-600 border-sky-100 uppercase tracking-tight cursor-default select-none"
                                                                >
                                                                    <Mail size={8} />
                                                                    EMAIL
                                                                </span>
                                                            )
                                                        )}

                                                        {(f.confidence !== undefined || ['n/a', 'na', 'null', '—'].includes((currentVal || '').toLowerCase().trim())) && (
                                                            <div className={`text-[9px] font-black px-1.5 py-0.5 rounded-md border flex items-center gap-1 ${['n/a', 'na', 'null', '—'].includes((currentVal || '').toLowerCase().trim()) ? 'bg-rose-50 text-rose-600 border-rose-100' : (f.confidence !== undefined && f.confidence >= 0.8
                                                                ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
                                                                : f.confidence !== undefined && f.confidence >= 0.6
                                                                    ? 'bg-amber-50 text-amber-600 border-amber-100'
                                                                    : 'bg-rose-50 text-rose-600 border-rose-100'
                                                            )}`}>
                                                                confidence score: {['n/a', 'na', 'null', '—'].includes((currentVal || '').toLowerCase().trim()) ? 'N/A' : `${(f.confidence! * 100).toFixed(0)}%`}
                                                            </div>
                                                        )}
                                                    </div>
                                                    {isEdited ? (
                                                        <div className="flex items-center gap-1">
                                                            {f.original && (
                                                                <button
                                                                    type="button"
                                                                    onClick={(e) => { e.stopPropagation(); setShowOriginal(isFocus ? null : f.label); }}
                                                                    className="text-amber-600 hover:bg-amber-100 p-0.5 rounded transition"
                                                                >
                                                                    <History size={11} />
                                                                </button>
                                                            )}
                                                            <span className="text-[9px] font-bold text-amber-600 bg-amber-100 px-1.5 py-0.5 rounded">MODIFIED</span>
                                                        </div>
                                                    ) : null}
                                                </div>

                                                {f.label.toLowerCase().includes('summary') || f.label.toLowerCase().includes('description') ? (
                                                    <textarea
                                                        value={currentVal || ''}
                                                        onChange={(e) => handleFieldChange(f.label, e.target.value)}
                                                        onClick={(e) => e.stopPropagation()}
                                                        onFocus={(e) => { e.stopPropagation(); onSelectField?.(f.id || f.label, f.traceability); }}
                                                        readOnly={isReadOnly}
                                                        rows={6}
                                                        className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none resize-none ${isReadOnly ? 'bg-slate-50 border-slate-200 font-semibold text-slate-600 cursor-default' :
                                                            f.error ? 'bg-red-50/40 border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-100 text-slate-700 font-semibold' :
                                                                isEdited ? 'bg-amber-50/50 border-amber-300 focus:border-amber-500 focus:ring-2 focus:ring-amber-200 text-slate-700 font-semibold' :
                                                                    'bg-white border-slate-200 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 text-slate-700 font-semibold'
                                                            }`}
                                                    />
                                                ) : (
                                                    <div className={f.tooltip ? 'relative group/tooltip' : undefined}>
                                                        <input
                                                            type="text"
                                                            value={currentVal || ''}
                                                            onChange={(e) => handleFieldChange(f.label, e.target.value)}
                                                            onClick={(e) => e.stopPropagation()}
                                                            onFocus={(e) => { e.stopPropagation(); onSelectField?.(f.id || f.label, f.traceability); }}
                                                            readOnly={isReadOnly}
                                                            className={`w-full px-3 py-2 text-sm rounded-lg border focus:outline-none ${isReadOnly ? 'bg-slate-50 border-slate-200 font-semibold text-slate-600 cursor-default' :
                                                                f.error ? 'bg-red-50/40 border-red-400 focus:border-red-500 focus:ring-2 focus:ring-red-100 text-slate-700 font-semibold' :
                                                                    isEdited ? 'bg-amber-50/50 border-amber-300 focus:border-amber-500 focus:ring-2 focus:ring-amber-200 text-slate-700 font-semibold' :
                                                                        'bg-white border-slate-200 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 text-slate-700 font-semibold'
                                                                }`}
                                                        />
                                                        {f.tooltip && (
                                                            <div className="absolute left-0 top-full mt-1.5 z-50 hidden group-hover/tooltip:block w-96 pointer-events-none">
                                                                {/* Arrow pointing up */}
                                                                <div className="w-2.5 h-2.5 bg-slate-800 rotate-45 ml-4 -mb-1.5" />
                                                                <div className="bg-slate-800 text-white text-xs rounded-xl px-3 py-2.5 shadow-xl leading-relaxed">
                                                                    <p className="text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">AI Summary</p>
                                                                    <p>{f.tooltip}</p>
                                                                </div>
                                                            </div>
                                                        )}
                                                    </div>
                                                )}

                                                {isFocus && f.original && (
                                                    <p className="text-[10px] text-slate-500 italic mt-0.5 flex items-center gap-1">
                                                        Original: {f.original}
                                                    </p>
                                                )}
                                                {f.error && (
                                                    <p className="text-[10px] text-red-500 flex items-center gap-1 mt-0.5">
                                                        <AlertTriangle size={10} /> {f.error}
                                                    </p>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>

            {!isReadOnly && hasEdits && (
                <div className="p-4 border-t border-amber-200 bg-amber-50/60 shrink-0 flex items-center justify-between gap-3">
                    <span className="text-xs font-semibold text-amber-700">
                        {Object.keys(editedFields).length} field{Object.keys(editedFields).length !== 1 ? 's' : ''} modified — save or cancel your changes
                    </span>
                    <div className="flex items-center gap-2">
                        {onFinalSubmit && (
                            <button
                                onClick={handleFinalSubmit}
                                disabled={isSaving}
                                className="px-5 py-2 rounded-xl font-bold text-sm flex items-center gap-2 transition-all bg-slate-900 text-white hover:bg-slate-800 active:scale-95 shadow-md"
                            >
                                {isSaving ? <><Loader2 size={15} className="animate-spin" /> Processing...</> : <>{finalSubmitLabel || 'Finalize & Proceed'} <ArrowRight size={15} /></>}
                            </button>
                        )}
                        <button
                            onClick={() => { setEditedFields({}); setShowOriginal(null); }}
                            disabled={isSaving}
                            className="px-5 py-2 rounded-xl font-bold text-sm flex items-center gap-2 transition-all bg-white text-slate-600 hover:bg-slate-100 border border-slate-300 active:scale-95"
                        >
                            <X size={15} /> Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={isSaving}
                            className="px-5 py-2 rounded-xl font-bold text-sm flex items-center gap-2 transition-all bg-indigo-600 text-white hover:bg-indigo-700 active:scale-95 shadow-md"
                        >
                            {isSaving ? <><Loader2 size={15} className="animate-spin" /> Saving...</> : <><CheckCircle2 size={15} /> Save Changes</>}
                        </button>
                    </div>
                </div>
            )}
            {!isReadOnly && !hasEdits && onFinalSubmit && (
                <div className="p-4 border-t border-slate-200 bg-slate-50/30 shrink-0 flex items-center justify-end">
                    <button
                        onClick={handleFinalSubmit}
                        disabled={isSaving}
                        className="px-6 py-2.5 rounded-xl font-bold text-sm flex items-center gap-2 transition-all bg-slate-900 text-white hover:bg-slate-800 active:scale-95 shadow-md"
                    >
                        {isSaving ? <><Loader2 size={16} className="animate-spin" /> Processing...</> : <>{finalSubmitLabel || 'Finalize & Proceed'} <ArrowRight size={16} /></>}
                    </button>
                </div>
            )}
        </div>
    );
}
