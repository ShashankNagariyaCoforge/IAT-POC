import React from 'react';
import { format } from 'date-fns';
import { AlertTriangle, CheckCircle, Clock, Mail, Zap } from 'lucide-react';
import { ConfidenceMeter } from './ConfidenceMeter';
import type { Case, TimelineEvent } from '../types';

interface CaseSummaryPanelProps {
    caseData: Case;
    timeline: TimelineEvent[];
}

const EVENT_ICON: Record<string, React.ReactNode> = {
    'Email received': <Mail className="w-3.5 h-3.5 text-blue-400" />,
    'Email classified': <Zap className="w-3.5 h-3.5 text-green-400" />,
    'Downstream notification sent': <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />,
};

export function CaseSummaryPanel({ caseData, timeline }: CaseSummaryPanelProps) {
    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Key details */}
            <div className="lg:col-span-2 space-y-5">
                {/* AI Summary */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-300 mb-3">AI Summary</h3>
                    <p className="text-slate-200 text-sm leading-relaxed">
                        {caseData.summary || 'Summary not yet available. Classification may still be in progress.'}
                    </p>
                    {caseData.requires_human_review && (
                        <div className="mt-4 flex items-center gap-2 bg-amber-900/20 border border-amber-800/50 rounded-lg px-3 py-2">
                            <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                            <span className="text-amber-300 text-sm">This case requires human review (confidence below threshold).</span>
                        </div>
                    )}
                </div>

                {/* Key fields */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                    <h3 className="text-sm font-semibold text-slate-300 mb-3">Case Details</h3>
                    <div className="grid grid-cols-2 gap-3">
                        {[
                            { label: 'Case ID', value: caseData.case_id },
                            { label: 'Subject', value: caseData.subject || '—' },
                            { label: 'Sender', value: caseData.sender },
                            { label: 'Email Count', value: caseData.email_count.toString() },
                            { label: 'Routing', value: caseData.routing_recommendation || '—' },
                            { label: 'Created', value: format(new Date(caseData.created_at), 'dd MMM yyyy HH:mm') },
                        ].map(field => (
                            <div key={field.label}>
                                <p className="text-slate-500 text-xs uppercase tracking-wider mb-0.5">{field.label}</p>
                                <p className="text-slate-200 text-sm truncate" title={field.value}>{field.value}</p>
                            </div>
                        ))}
                        <div>
                            <p className="text-slate-500 text-xs uppercase tracking-wider mb-0.5">Confidence</p>
                            <ConfidenceMeter score={caseData.confidence_score} />
                        </div>
                    </div>
                </div>
            </div>

            {/* Timeline */}
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <h3 className="text-sm font-semibold text-slate-300 mb-4">Processing Timeline</h3>
                {timeline.length === 0 ? (
                    <p className="text-slate-500 text-sm">No events recorded yet.</p>
                ) : (
                    <ol className="relative border-l border-slate-700 ml-2 space-y-5">
                        {timeline.map((event, i) => (
                            <li key={i} className="ml-4">
                                <div className="absolute -left-1.5 w-3 h-3 bg-slate-700 border border-slate-600 rounded-full flex items-center justify-center mt-1">
                                    <div className="w-1.5 h-1.5 bg-blue-400 rounded-full" />
                                </div>
                                <div className="flex items-start gap-2">
                                    {EVENT_ICON[event.event] || <Clock className="w-3.5 h-3.5 text-slate-500 mt-0.5" />}
                                    <div>
                                        <p className="text-slate-200 text-sm font-medium">{event.event}</p>
                                        {event.details && <p className="text-slate-400 text-xs mt-0.5">{event.details}</p>}
                                        {event.timestamp && (
                                            <p className="text-slate-600 text-xs mt-0.5">
                                                {format(new Date(event.timestamp), 'dd MMM HH:mm:ss')}
                                            </p>
                                        )}
                                    </div>
                                </div>
                            </li>
                        ))}
                    </ol>
                )}
            </div>
        </div>
    );
}
