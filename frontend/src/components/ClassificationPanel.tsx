import React from 'react';
import { format } from 'date-fns';
import { CheckCircle2, Clock, AlertTriangle } from 'lucide-react';
import { ConfidenceMeter } from './ConfidenceMeter';
import { CategoryBadge } from './CategoryBadge';
import type { ClassificationResult } from '../types';

interface ClassificationPanelProps {
    classification: ClassificationResult | null;
}

export function ClassificationPanel({ classification }: ClassificationPanelProps) {
    if (!classification) {
        return (
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 text-center text-slate-500">
                Classification not yet available. Processing may still be in progress.
            </div>
        );
    }

    const urgencyColor = {
        high: 'text-red-400',
        medium: 'text-amber-400',
        low: 'text-green-400',
    }[classification.key_fields?.urgency ?? 'low'] || 'text-slate-400';

    return (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Main classification */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-5">
                <div>
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Classification</p>
                    <CategoryBadge category={classification.classification_category} />
                </div>
                <div>
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Confidence Score</p>
                    <div className="max-w-xs">
                        <ConfidenceMeter score={classification.confidence_score} />
                    </div>
                    <p className="text-slate-500 text-xs mt-1">
                        Threshold: 75% — {classification.requires_human_review
                            ? 'Below threshold, human review recommended'
                            : 'Above threshold'}
                    </p>
                </div>
                {classification.requires_human_review && (
                    <div className="flex items-center gap-2 bg-amber-900/20 border border-amber-800/50 rounded-lg px-3 py-2">
                        <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                        <span className="text-amber-300 text-sm">Human review required</span>
                    </div>
                )}
                <div>
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Routing Recommendation</p>
                    <p className="text-slate-200 text-sm">{classification.routing_recommendation || '—'}</p>
                </div>
                <div>
                    <p className="text-slate-400 text-xs uppercase tracking-wider mb-2">Summary</p>
                    <p className="text-slate-200 text-sm leading-relaxed">{classification.summary}</p>
                </div>
            </div>

            {/* Key fields + notification */}
            <div className="space-y-5">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h4 className="text-sm font-semibold text-slate-300 mb-4">Extracted Key Fields</h4>
                    <div className="grid grid-cols-2 gap-3">
                        {[
                            { label: 'Document Type', value: classification.key_fields?.document_type || '—' },
                            { label: 'Urgency', value: classification.key_fields?.urgency || '—', className: urgencyColor },
                            { label: 'Policy Reference', value: classification.key_fields?.policy_reference || '—' },
                            { label: 'Claim Type', value: classification.key_fields?.claim_type || '—' },
                        ].map(field => (
                            <div key={field.label}>
                                <p className="text-slate-500 text-xs uppercase tracking-wider mb-0.5">{field.label}</p>
                                <p className={`text-sm font-medium ${field.className ?? 'text-slate-200'}`}>{field.value}</p>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Downstream notification */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h4 className="text-sm font-semibold text-slate-300 mb-4">Downstream Notification</h4>
                    <div className="flex items-center gap-3">
                        {classification.downstream_notification_sent ? (
                            <>
                                <CheckCircle2 className="w-5 h-5 text-green-400 flex-shrink-0" />
                                <div>
                                    <p className="text-green-300 text-sm font-medium">Notification sent</p>
                                    {classification.downstream_notification_at && (
                                        <p className="text-slate-500 text-xs mt-0.5">
                                            {format(new Date(classification.downstream_notification_at), 'dd MMM yyyy HH:mm:ss')}
                                        </p>
                                    )}
                                </div>
                            </>
                        ) : (
                            <>
                                <Clock className="w-5 h-5 text-slate-500 flex-shrink-0" />
                                <p className="text-slate-400 text-sm">Notification pending</p>
                            </>
                        )}
                    </div>
                </div>

                {/* Meta */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h4 className="text-sm font-semibold text-slate-300 mb-3">Classification Metadata</h4>
                    <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                            <span className="text-slate-500">Result ID</span>
                            <span className="text-slate-400 font-mono">{classification.result_id.slice(0, 8)}…</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-500">Classified At</span>
                            <span className="text-slate-400">
                                {format(new Date(classification.classified_at), 'dd MMM yyyy HH:mm:ss')}
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
