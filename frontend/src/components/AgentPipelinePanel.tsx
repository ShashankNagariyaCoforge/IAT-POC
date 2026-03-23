import { useEffect, useRef, useState, useMemo } from 'react';
import {
    Network, Mail, Fingerprint, ShieldCheck, BrainCircuit,
    CheckCircle2, XCircle, Loader2, FileText, Globe
} from 'lucide-react';
import { createApiClient, casesApi } from '../api/casesApi';
import { useMsal } from '@azure/msal-react';
import type { AgentStatus, PipelineStatus } from '../types';
import { formatDistanceToNow } from 'date-fns';

const AGENT_ICONS: Record<string, React.ReactNode> = {
    orchestrator: <Network size={16} />,
    email: <Mail size={16} />,
    pii: <Fingerprint size={16} />,
    safety: <ShieldCheck size={16} />,
    classifier: <BrainCircuit size={16} />,
    extraction: <FileText size={16} />,
    enrichment: <Globe size={16} />,
};

function VerticalAgentCard({ agent, isActive, isLast }: { agent: AgentStatus; isActive: boolean; isLast: boolean }) {
    const isCompleted = agent.status === 'completed';
    const isFailed = agent.status === 'failed';
    const isWarning = agent.status === 'warning';
    const isPending = agent.status === 'pending';

    let iconBoxClass = "border-slate-300 text-slate-400";
    if (isCompleted) iconBoxClass = "border-indigo-500 text-indigo-500 shadow-md shadow-indigo-500/50";
    else if (isActive) iconBoxClass = "border-cyan-500 text-cyan-500 shadow-md shadow-cyan-500/40 ring-1 ring-cyan-500";
    else if (isWarning) iconBoxClass = "border-amber-500 text-amber-500 shadow-md shadow-amber-500/50";
    else if (isFailed) iconBoxClass = "border-red-500 text-red-500 shadow-md shadow-red-500/40 ring-1 ring-red-500";

    return (
        <div className="flex gap-4">
            <div className="flex flex-col items-center">
                <div className="relative shrink-0">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-500 bg-white border ${iconBoxClass}`}>
                        {AGENT_ICONS[agent.id] || <BrainCircuit size={16} />}
                    </div>
                    {isActive && (
                        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white rounded-full flex items-center justify-center shadow-sm ring-1 ring-cyan-100 z-10">
                            <Loader2 className="animate-spin text-cyan-500" size={14} />
                        </div>
                    )}
                    {isCompleted && (
                        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white rounded-full flex items-center justify-center shadow-sm ring-1 ring-indigo-100 z-10">
                            <CheckCircle2 className="text-indigo-500" size={14} />
                        </div>
                    )}
                    {isFailed && (
                        <div className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-white rounded-full flex items-center justify-center shadow-sm ring-1 ring-red-100 z-10">
                            <XCircle className="text-red-500" size={14} />
                        </div>
                    )}
                </div>

                {!isLast && (
                    <div className={`w-0.5 flex-1 min-h-[36px] my-1.5 rounded-full transition-all duration-700 ${isCompleted ? 'bg-gradient-to-b from-indigo-400 to-indigo-100' : 'bg-slate-200'}`} />
                )}
            </div>

            <div className="pb-6 min-w-0 flex-1 pt-1">
                <div className="flex items-center gap-2 mb-1">
                    <h4 className={`text-sm font-bold leading-tight transition-colors duration-300 ${isCompleted ? "text-slate-800" : isActive ? "text-slate-900" : "text-slate-400"}`}>
                        {agent.name}
                    </h4>
                    {!isPending && (
                        <span className="text-[9px] font-black uppercase tracking-widest text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">{agent.type}</span>
                    )}
                </div>

                <p className={`text-xs leading-relaxed transition-colors duration-300 mb-2 ${isActive ? "text-cyan-600 font-medium" : isCompleted ? "text-slate-600" : "text-slate-500"}`}>
                    {agent.detail}
                </p>

                {agent.score > 0 && !isPending && (
                    <div className="flex items-center gap-2 mt-2">
                        <div className="flex items-baseline gap-0.5">
                            <span className={`text-[12px] font-black leading-none tabular-nums ${isCompleted ? "text-indigo-600" : isActive ? "text-cyan-600" : "text-slate-400"}`}>
                                {agent.score}
                            </span>
                            <span className="text-[10px] font-bold text-slate-400">%</span>
                        </div>
                        <div className="flex-1 max-w-[120px]">
                            <div className="w-full h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-1000 ease-out ${isCompleted ? "bg-gradient-to-r from-indigo-400 to-indigo-500" : isActive ? "bg-gradient-to-r from-cyan-400 to-cyan-500" : "bg-slate-300"}`}
                                    style={{ width: `${agent.score}%` }}
                                />
                            </div>
                        </div>
                        <span className={`text-[9px] font-bold uppercase tracking-widest ${isCompleted ? "text-indigo-500" : isActive ? "text-cyan-500" : "text-slate-400"}`}>
                            Confidence
                        </span>
                    </div>
                )}
            </div>
        </div>
    );
}

interface AgentPipelinePanelProps {
    caseId: string;
    initialStatus?: PipelineStatus | null;
    initialRevealIndex?: number;
    onStatusChange?: (status: PipelineStatus) => void;
    onRevealIndexChange?: (index: number) => void;
    compact?: boolean;
    skipPii?: boolean;
}

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export function AgentPipelinePanel({ caseId, initialStatus, initialRevealIndex, onStatusChange, onRevealIndexChange, compact = false, skipPii = false }: AgentPipelinePanelProps) {
    const { instance } = useMsal();
    const apiClient = useMemo(() => (DEV_BYPASS_AUTH ? createApiClient(instance) : createApiClient(instance)), [instance]);
    const [pipeline, setPipeline] = useState<PipelineStatus | null>(initialStatus ?? null);
    const [revealIndex, setRevealIndex] = useState(initialRevealIndex ?? 0);
    const [loading, setLoading] = useState(!initialStatus);
    const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const [lastActivity, setLastActivity] = useState<Date>(new Date());

    const fetchStatus = async () => {
        try {
            const data = await casesApi.getPipelineStatus(apiClient, caseId);
            setPipeline(data);
            setLastActivity(new Date());
            onStatusChange?.(data);
            return data;
        } catch {
            return null;
        }
    };

    useEffect(() => {
        let cancelled = false;

        const poll = async () => {
            if (cancelled) return;
            const data = await fetchStatus();
            setLoading(false);
            if (!data?.is_terminal && !cancelled) {
                pollRef.current = setTimeout(poll, 2500);
            }
        };

        poll();

        return () => {
            cancelled = true;
            if (pollRef.current) clearTimeout(pollRef.current);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId]);

    // Staggered reveal effect
    useEffect(() => {
        if (!pipeline) return;
        const targetIndex = pipeline.current_agent_index;

        if (revealIndex < targetIndex || (pipeline.is_terminal && revealIndex < pipeline.agents.length)) {
            const tm = setTimeout(() => {
                const next = revealIndex + 1;
                setRevealIndex(next);
                onRevealIndexChange?.(next);
            }, 600);
            return () => clearTimeout(tm);
        }
    }, [pipeline, revealIndex, onRevealIndexChange]);

    if (loading) return (
        <div className="flex flex-col items-center justify-center h-48 gap-3 bg-white border border-slate-200 rounded-[24px] shadow-sm">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-400 to-indigo-600 flex items-center justify-center shadow-lg shadow-indigo-200/50">
                <Loader2 className="animate-spin text-white" size={20} />
            </div>
            <div className="text-center">
                <p className="text-sm font-bold text-slate-800">Initializing AI Agents</p>
                <p className="text-xs text-slate-500 mt-0.5">Setting up orchestration pipeline...</p>
            </div>
        </div>
    );

    if (!pipeline) return null;

    // Filter agents based on skipPii (if backend hasn't already filtered them, or if we want immediate UI feedback)
    const displayAgents = skipPii ? pipeline.agents.filter(a => a.id !== 'pii') : pipeline.agents;

    return (
        <div className={`bg-white border border-slate-200 rounded-[24px] ${compact ? 'p-4' : 'p-6'} shadow-sm flex flex-col h-full`}>
            {/* Header */}
            <div className="flex items-center justify-between mb-8 pb-4 border-b border-slate-100">
                <div>
                    <h3 className="text-lg font-black text-slate-800 tracking-tight">Agent Intelligence Flow</h3>
                    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mt-1">Multi-Agent Orchestration</p>
                </div>
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${pipeline.is_terminal ? 'bg-emerald-50 border-emerald-200' : 'bg-indigo-50 border-indigo-200'}`}>
                    <div className={`w-2 h-2 rounded-full ${pipeline.is_terminal ? 'bg-emerald-500' : 'bg-indigo-500 animate-pulse'}`} />
                    <span className={`text-[10px] font-black uppercase tracking-widest ${pipeline.is_terminal ? 'text-emerald-700' : 'text-indigo-700'}`}>
                        {pipeline.is_terminal ? 'Completed' : 'Syncing'}
                    </span>
                </div>
            </div>

            {/* Vertical Flow */}
            <div className="flex-1">
                {displayAgents.map((agent, i) => {
                    const isRevealed = i <= revealIndex;
                    const displayAgentData = isRevealed ? agent : { ...agent, status: 'pending', detail: 'Pending execution...', score: 0 };

                    return (
                        <div
                            key={agent.id}
                            className={`transition-all duration-700 ease-out ${isRevealed ? "opacity-100 translate-y-0" : "opacity-40 translate-y-4"}`}
                        >
                            <VerticalAgentCard
                                agent={displayAgentData as AgentStatus}
                                isActive={agent.status === 'active' && i === pipeline.current_agent_index && isRevealed}
                                isLast={i === displayAgents.length - 1}
                            />
                        </div>
                    );
                })}
            </div>

            {/* Footer */}
            {!pipeline.is_terminal && (
                <div className="mt-4 pt-4 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                        <div className="flex flex-col gap-0.5">
                            <span className="text-[9px] font-black uppercase tracking-widest text-slate-400">Live Status</span>
                            <span className="text-[11px] font-medium text-slate-500">
                                Last activity: {formatDistanceToNow(lastActivity, { addSuffix: true })}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
