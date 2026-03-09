import { useEffect, useRef, useState } from 'react';
import {
    Network, Mail, Fingerprint, ShieldCheck, BrainCircuit,
    CheckCircle2, XCircle, AlertTriangle, Loader2,
} from 'lucide-react';
import { createApiClient } from '../api/casesApi';
import { casesApi } from '../api/casesApi';
import { useMsal } from '@azure/msal-react';
import type { AgentStatus, PipelineStatus } from '../types';

const AGENT_ICONS: Record<string, React.ReactNode> = {
    orchestrator: <Network size={22} />,
    email: <Mail size={22} />,
    pii: <Fingerprint size={22} />,
    safety: <ShieldCheck size={22} />,
    classifier: <BrainCircuit size={22} />,
};

const STATUS_COLORS = {
    pending: { bg: '#f1f5f9', border: '#e2e8f0', icon: '#cbd5e1', text: '#94a3b8' },
    active: { bg: '#eef2ff', border: '#818cf8', icon: '#4f46e5', text: '#4f46e5' },
    completed: { bg: '#ecfdf5', border: '#6ee7b7', icon: '#059669', text: '#059669' },
    failed: { bg: '#fff1f2', border: '#fda4af', icon: '#e11d48', text: '#e11d48' },
    warning: { bg: '#fffbeb', border: '#fcd34d', icon: '#d97706', text: '#d97706' },
};

function AgentStatusIcon({ status }: { status: string }) {
    if (status === 'active') return <Loader2 size={14} className="animate-spin" style={{ color: '#4f46e5' }} />;
    if (status === 'completed') return <CheckCircle2 size={14} style={{ color: '#059669' }} />;
    if (status === 'failed') return <XCircle size={14} style={{ color: '#e11d48' }} />;
    if (status === 'warning') return <AlertTriangle size={14} style={{ color: '#d97706' }} />;
    return null;
}

interface AgentCardProps {
    agent: AgentStatus;
    isActive: boolean;
}

function AgentCard({ agent, isActive }: AgentCardProps) {
    const colors = STATUS_COLORS[agent.status] ?? STATUS_COLORS.pending;

    return (
        <div style={{
            background: '#ffffff',
            border: `1.5px solid ${isActive ? '#4f46e5' : colors.border}`,
            borderRadius: '20px',
            padding: '20px',
            flex: 1,
            minWidth: 0,
            boxShadow: isActive ? '0 8px 24px rgba(79,70,229,0.15)' : '0 1px 4px rgba(0,0,0,0.04)',
            transition: 'all 0.4s ease',
            position: 'relative',
            overflow: 'hidden',
        }}>
            {/* Active pulse background */}
            {isActive && (
                <div style={{
                    position: 'absolute', inset: 0,
                    background: 'linear-gradient(135deg, rgba(79,70,229,0.04), transparent)',
                    borderRadius: '20px',
                }} />
            )}

            {/* Icon box */}
            <div style={{
                width: '44px', height: '44px', borderRadius: '12px',
                background: colors.bg,
                border: `1px solid ${colors.border}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                marginBottom: '14px', color: colors.icon,
                transform: isActive ? 'scale(1.05)' : 'scale(1)',
                transition: 'transform 0.3s',
            }}>
                {AGENT_ICONS[agent.id]}
            </div>

            {/* Type badge */}
            <div style={{
                display: 'inline-flex', alignItems: 'center', gap: '4px',
                marginBottom: '8px',
            }}>
                <span style={{
                    fontSize: '9px', fontWeight: 800, textTransform: 'uppercase',
                    letterSpacing: '0.12em', color: colors.text,
                    background: colors.bg, border: `1px solid ${colors.border}`,
                    padding: '2px 8px', borderRadius: '6px',
                }}>{agent.type}</span>
                {agent.status !== 'pending' && <AgentStatusIcon status={agent.status} />}
            </div>

            <h4 style={{
                margin: '0 0 4px 0', fontSize: '13px', fontWeight: 800,
                color: '#0f172a', letterSpacing: '-0.01em',
            }}>{agent.name}</h4>

            <p style={{ margin: '0 0 12px 0', fontSize: '11px', color: '#94a3b8', fontWeight: 500 }}>
                {agent.detail}
            </p>

            {/* Score progress bar */}
            {agent.score > 0 && (
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#cbd5e1' }}>
                            Model Score
                        </span>
                        <span style={{ fontSize: '12px', fontWeight: 900, color: '#0f172a' }}>{agent.score}%</span>
                    </div>
                    <div style={{ height: '4px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden' }}>
                        <div style={{
                            height: '100%', borderRadius: '999px',
                            background: agent.score >= 90 ? '#4f46e5' : agent.score >= 70 ? '#f59e0b' : '#e11d48',
                            width: `${agent.score}%`,
                            transition: 'width 1s ease',
                        }} />
                    </div>
                </div>
            )}
        </div>
    );
}

interface AgentPipelinePanelProps {
    caseId: string;
    initialStatus?: PipelineStatus | null;
    initialRevealIndex?: number;
    /** Called whenever the pipeline status updates (e.g., to propagate status to parent) */
    onStatusChange?: (status: PipelineStatus) => void;
    onRevealIndexChange?: (index: number) => void;
    compact?: boolean;
}

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

export function AgentPipelinePanel({ caseId, initialStatus, initialRevealIndex, onStatusChange, onRevealIndexChange, compact = false }: AgentPipelinePanelProps) {
    const { instance } = useMsal();
    const apiClient = DEV_BYPASS_AUTH ? createApiClient(instance) : createApiClient(instance);
    const [pipeline, setPipeline] = useState<PipelineStatus | null>(initialStatus ?? null);
    const [revealIndex, setRevealIndex] = useState(initialRevealIndex ?? 0);
    const [loading, setLoading] = useState(!initialStatus);
    const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const fetchStatus = async () => {
        try {
            const data = await casesApi.getPipelineStatus(apiClient, caseId);
            setPipeline(data);
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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px', gap: '12px', color: '#94a3b8' }}>
            <Loader2 size={20} className="animate-spin" />
            <span style={{ fontSize: '13px', fontWeight: 600 }}>Loading pipeline…</span>
        </div>
    );

    if (!pipeline) return null;

    const progressPct = pipeline.agents.length > 1
        ? (pipeline.current_agent_index / (pipeline.agents.length - 1)) * 100
        : 0;

    return (
        <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: compact ? '16px' : '24px', padding: compact ? '20px' : '28px', boxShadow: '0 2px 12px rgba(0,0,0,0.04)' }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                <div>
                    <p style={{ margin: 0, fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#94a3b8' }}>
                        Agentic Pipeline
                    </p>
                    <h3 style={{ margin: '2px 0 0 0', fontSize: '16px', fontWeight: 800, color: '#0f172a', letterSpacing: '-0.01em' }}>
                        Agent Intelligence Flow
                    </h3>
                </div>
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '6px',
                    background: pipeline.is_terminal ? '#ecfdf5' : '#eef2ff',
                    border: `1px solid ${pipeline.is_terminal ? '#6ee7b7' : '#818cf8'}`,
                    padding: '5px 12px', borderRadius: '8px',
                }}>
                    <div style={{
                        width: '6px', height: '6px', borderRadius: '50%',
                        background: pipeline.is_terminal ? '#059669' : '#4f46e5',
                        animation: pipeline.is_terminal ? 'none' : 'ping 1.5s ease-in-out infinite',
                    }} />
                    <span style={{
                        fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em',
                        color: pipeline.is_terminal ? '#059669' : '#4f46e5',
                    }}>
                        {pipeline.is_terminal ? 'Completed' : 'Processing'}
                    </span>
                </div>
            </div>

            {/* Progress connector line */}
            <div style={{ position: 'relative', marginBottom: '20px', display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                {/* Agent cards */}
                {pipeline.agents.map((agent, i) => {
                    const isVisible = i <= revealIndex;
                    if (!isVisible) return <div key={agent.id} style={{ flex: 1, minWidth: 0 }} />;
                    return (
                        <div key={agent.id} style={{ flex: 1, minWidth: 0, animation: 'fadeIn 0.4s ease-out forwards' }}>
                            <AgentCard
                                agent={agent}
                                isActive={agent.status === 'active' && i === pipeline.current_agent_index}
                            />
                        </div>
                    );
                })}
            </div>

            {/* Bottom progress bar */}
            <div style={{ height: '3px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden' }}>
                <div style={{
                    height: '100%', borderRadius: '999px',
                    background: 'linear-gradient(90deg, #4f46e5, #818cf8)',
                    width: pipeline.is_terminal ? '100%' : `${progressPct}%`,
                    transition: 'width 0.8s ease',
                    boxShadow: '0 0 8px rgba(79,70,229,0.4)',
                }} />
            </div>
        </div>
    );
}
