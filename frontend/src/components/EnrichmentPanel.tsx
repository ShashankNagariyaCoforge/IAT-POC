import { useState, useEffect, useMemo } from 'react';
import { Globe, ExternalLink, ChevronDown, ChevronUp, Loader2, AlertCircle } from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { useMsal } from '@azure/msal-react';
import type { EnrichedField, EnrichmentData } from '../types';

/** Human-readable label for field keys */
const FIELD_LABELS: Record<string, string> = {
    entity_type: 'Entity Type',
    naics_code: 'NAICS Code',
    entity_structure: 'Entity Structure',
    years_in_business: 'Years in Business',
    number_of_employees: 'Number of Employees',
    territory_code: 'Territory Code',
    limit_of_liability: 'Limit of Liability',
    deductible: 'Deductible',
    class_mass_action_deductible_retention: 'Class/Mass Action Ded. Retention',
    pending_or_prior_litigation_date: 'Pending/Prior Litigation Date',
    duty_to_defend_limit: 'Duty to Defend Limit',
    defense_outside_limit: 'Defense Outside Limit',
    employment_category: 'Employment Category',
    ec_number_of_employees: 'EC Number of Employees',
    employee_compensation: 'Employee Compensation',
    number_of_employees_in_each_band: 'Employees per Band',
    employee_location: 'Employee Location(s)',
    number_of_employees_in_each_location: 'Employees per Location',
};

/** Extractable field keys (matching backend model) */
const FIELD_KEYS = Object.keys(FIELD_LABELS);

function ConfidenceBadge({ confidence, isNA = false }: { confidence: number; isNA?: boolean }) {
    const pct = Math.round(confidence * 100);
    const colorClass = isNA ? 'bg-rose-50 text-rose-600 border-rose-100' : (
        confidence >= 0.8
            ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
            : confidence >= 0.5
                ? 'bg-amber-50 text-amber-600 border-amber-100'
                : 'bg-rose-50 text-rose-600 border-rose-100'
    );

    return (
        <div className={`px-2 py-0.5 rounded-full border text-[10px] font-black uppercase tracking-tight flex items-center gap-1.5 ${colorClass}`}>
            <div className={`w-1.5 h-1.5 rounded-full ${isNA ? 'bg-rose-500' : (confidence >= 0.8 ? 'bg-emerald-500' : confidence >= 0.5 ? 'bg-amber-500' : 'bg-rose-500')}`} />
            confidence score: {isNA ? 'N/A' : `${pct}%`}
        </div>
    );
}

function ConfidenceBar({ confidence, isNA = false }: { confidence: number; isNA?: boolean }) {
    if (isNA) {
        return (
            <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full rounded-full transition-all duration-500 bg-slate-300" style={{ width: '100%' }} />
            </div>
        );
    }
    const pct = Math.round(confidence * 100);
    const barColor =
        confidence >= 0.8
            ? 'bg-emerald-400'
            : confidence >= 0.5
                ? 'bg-amber-400'
                : 'bg-rose-400';
    return (
        <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className={`h-full rounded-full transition-all duration-500 ${barColor}`} style={{ width: `${pct}%` }} />
        </div>
    );
}

interface EnrichmentPanelProps {
    caseId: string;
}

export function EnrichmentPanel({ caseId }: EnrichmentPanelProps) {
    const { instance } = useMsal();
    const [enrichmentData, setEnrichmentData] = useState<EnrichmentData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [showSources, setShowSources] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            setLoading(true);
            setError(null);
            try {
                const client = createApiClient(instance);
                const resp = await casesApi.getCaseEnrichment(client, caseId);
                if (!cancelled) {
                    const result = resp?.enrichment;
                    if (result && (result as any).enrichment) {
                        setEnrichmentData((result as any).enrichment);
                    } else {
                        setEnrichmentData(null);
                    }
                }
            } catch (e: any) {
                if (!cancelled) {
                    setError(e?.message || 'Failed to load enrichment');
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        };
        load();
        return () => { cancelled = true; };
    }, [caseId, instance]);

    const fields = useMemo(() => {
        if (!enrichmentData) return [];
        return FIELD_KEYS
            .map(key => {
                const f = (enrichmentData as any)[key] as EnrichedField | undefined;
                return {
                    key,
                    label: FIELD_LABELS[key],
                    value: f?.value || null,
                    confidence: f?.confidence || 0,
                    source: f?.source || null,
                    isCritical: f?.is_critical || false, // Add isCritical property
                };
            })
            .filter(f => f.value !== null);
    }, [enrichmentData]);

    const avgConfidence = useMemo(() => {
        if (fields.length === 0) return 0;
        const validFields = fields.filter(f => f.value !== 'NA');
        if (validFields.length === 0) return 0; // All fields are N/A
        return validFields.reduce((sum, f) => sum + f.confidence, 0) / validFields.length;
    }, [fields]);

    if (loading) {
        return (
            <div className="bg-white rounded-2xl border shadow-sm p-6 flex items-center justify-center gap-2 text-slate-400">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm font-medium">Loading enrichment data…</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-white rounded-2xl border shadow-sm p-6 flex items-center gap-2 text-rose-500">
                <AlertCircle size={16} />
                <span className="text-sm font-medium">{error}</span>
            </div>
        );
    }

    if (!enrichmentData) {
        return null;
    }

    const hasFields = fields.length > 0;

    return (
        <div className="bg-white rounded-2xl border shadow-sm overflow-hidden flex-shrink-0 min-h-[450px] flex flex-col">
            {/* Header */}
            <div className="px-6 py-4 border-b bg-gradient-to-r from-cyan-50/80 to-emerald-50/60 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500 to-emerald-500 flex items-center justify-center shadow-sm">
                        <Globe size={16} className="text-white" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-slate-800">Web Enrichment</h2>
                        <p className="text-[10px] text-slate-500 mt-0.5">
                            {fields.length} fields enriched • Avg confidence: {Math.round(avgConfidence * 100)}%
                            {enrichmentData.company_name && ` • ${enrichmentData.company_name}`}
                        </p>
                    </div>
                </div>
                <ConfidenceBadge confidence={avgConfidence} />
            </div>

            {/* Body */}
            <div className="p-6 flex-1 max-h-[700px] overflow-y-auto custom-scrollbar">
                {hasFields ? (
                    <div className="grid grid-cols-2 gap-4 pb-12">
                        {fields.map(f => (
                            <div key={f.key} className="p-3 rounded-xl bg-slate-50 border border-slate-100 hover:border-cyan-200 transition-colors group">
                                <div className="flex items-center justify-between mb-1.5">
                                    <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">
                                        {f.label}
                                    </span>
                                    <div className="flex items-center justify-between mb-1.5">
                                        <ConfidenceBadge confidence={f.confidence} isNA={!f.value || ['n/a', 'na', 'null', '—'].includes(f.value.toLowerCase().trim())} />
                                        {f.isCritical && (
                                            <span className="text-[9px] font-black text-rose-500 bg-rose-50 px-1.5 py-0.5 rounded border border-rose-100">CRITICAL</span>
                                        )}
                                    </div>
                                </div>
                                <p className="text-sm font-semibold text-slate-800 mb-2 break-words">{f.value || '—'}</p>
                                <ConfidenceBar confidence={f.confidence} isNA={!f.value || ['n/a', 'na', 'null', '—'].includes(f.value.toLowerCase().trim())} />
                                <div className="mt-1.5">
                                    {f.source && f.source.startsWith('http') ? (
                                        <a
                                            href={f.source}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-[9px] text-cyan-600 hover:text-cyan-700 flex items-center gap-0.5 truncate max-w-full"
                                        >
                                            <ExternalLink size={9} className="shrink-0" />
                                            {new URL(f.source).hostname}
                                        </a>
                                    ) : (
                                        <span className="text-[9px] text-slate-400 flex items-center gap-0.5">
                                            <svg viewBox="0 0 12 12" width="9" height="9" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M2 2h8v8H2z"/><path d="M4 5h4M4 7h3"/></svg>
                                            Submission Documents
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-8 px-4 text-center bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                        <Globe size={24} className="text-slate-300 mb-2" />
                        <h3 className="text-sm font-bold text-slate-600 mb-1">Entity Identified</h3>
                        <p className="text-[11px] text-slate-400 max-w-[240px]">
                            We've identified <strong>{enrichmentData.company_name}</strong>, but no additional enriched fields were found in public web records at this time.
                        </p>
                    </div>
                )}

                {/* Source URLs collapsible */}
                {(() => {
                    const validUrls = (enrichmentData.source_urls ?? []).filter(u => u !== 'google_search' && u !== 'source_text' && u.startsWith('http'));
                    return validUrls.length > 0 ? (
                    <div className="mt-4 border-t border-slate-100 pt-3">
                        <button
                            onClick={() => setShowSources(!showSources)}
                            className="flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-700 transition-colors"
                        >
                            {showSources ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                            {validUrls.length} source URL{validUrls.length !== 1 ? 's' : ''}
                        </button>
                        {showSources && (
                            <div className="mt-2 space-y-1">
                                {validUrls
                                    .map((url, i) => (
                                        <a
                                            key={i}
                                            href={url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="flex items-center gap-1.5 text-xs text-cyan-600 hover:text-cyan-700 hover:underline truncate"
                                        >
                                            <ExternalLink size={10} className="shrink-0" />
                                            {url}
                                        </a>
                                    ))}
                            </div>
                        )}
                    </div>
                    ) : null;
                })()}
            </div>
        </div>
    );
}
