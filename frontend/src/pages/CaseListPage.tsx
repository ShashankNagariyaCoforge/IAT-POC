import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    Search, AlertTriangle, ChevronUp, ChevronDown, LogOut, RefreshCw, X,
    Activity, CheckCircle2, Clock, Users, Zap, Network, Mail, Fingerprint, ShieldCheck, BrainCircuit,
    Loader2, ChevronRight,
} from 'lucide-react';
import { createApiClient, casesApi, ListCasesParams } from '../api/casesApi';
import type { Case, ClassificationCategory, CaseStatus } from '../types';
import { format } from 'date-fns';
import { StatCard } from '../components/StatCard';

const CATEGORIES: ClassificationCategory[] = [
    'New', 'Renewal', 'Query/General', 'Follow-up',
    'Complaint/Escalation', 'Regulatory/Legal', 'Documentation/Evidence', 'Spam/Irrelevant',
];
const STATUSES: CaseStatus[] = ['RECEIVED', 'PROCESSING', 'CLASSIFIED', 'PENDING_REVIEW', 'PROCESSED', 'FAILED', 'BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY'];

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

// ── Status pill styles ──────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, { bg: string; border: string; color: string; label: string }> = {
    RECEIVED: { bg: '#f0f9ff', border: '#bae6fd', color: '#0369a1', label: 'Received' },
    PROCESSING: { bg: '#eef2ff', border: '#a5b4fc', color: '#4338ca', label: 'Processing' },
    CLASSIFIED: { bg: '#f0fdf4', border: '#86efac', color: '#15803d', label: 'Classified' },
    PROCESSED: { bg: '#f0fdf4', border: '#86efac', color: '#15803d', label: 'Processed' },
    PENDING_REVIEW: { bg: '#fefce8', border: '#fde047', color: '#a16207', label: 'Pending Review' },
    FAILED: { bg: '#fff1f2', border: '#fda4af', color: '#be123c', label: 'Failed' },
    BLOCKED_SAFETY: { bg: '#fff1f2', border: '#fda4af', color: '#be123c', label: 'Blocked' },
    NEEDS_REVIEW_SAFETY: { bg: '#fffbeb', border: '#fcd34d', color: '#b45309', label: 'Safety Review' },
};

const CATEGORY_STYLES: Record<string, { bg: string; border: string; color: string }> = {
    'New': { bg: '#eef2ff', border: '#c7d2fe', color: '#4338ca' },
    'Renewal': { bg: '#f0fdf4', border: '#bbf7d0', color: '#15803d' },
    'Query/General': { bg: '#f0f9ff', border: '#bae6fd', color: '#0284c7' },
    'Follow-up': { bg: '#fdf4ff', border: '#e9d5ff', color: '#7e22ce' },
    'Complaint/Escalation': { bg: '#fff1f2', border: '#fecdd3', color: '#be123c' },
    'Regulatory/Legal': { bg: '#fff7ed', border: '#fed7aa', color: '#c2410c' },
    'Documentation/Evidence': { bg: '#f0fdf4', border: '#bbf7d0', color: '#166534' },
    'Spam/Irrelevant': { bg: '#f8fafc', border: '#cbd5e1', color: '#64748b' },
};

// ── Sync pipeline animation ────────────────────────────────────────────────
const SYNC_AGENTS = [
    { id: 'orchestrator', name: 'Orchestrator', icon: Network },
    { id: 'email', name: 'Email Agent', icon: Mail },
    { id: 'pii', name: 'PII Agent', icon: Fingerprint },
    { id: 'safety', name: 'Content Safety', icon: ShieldCheck },
    { id: 'classifier', name: 'Classification', icon: BrainCircuit },
];

function SyncPipelineModal({ onClose }: { onClose: () => void }) {
    const [activeIdx, setActiveIdx] = useState(0);

    useEffect(() => {
        const interval = setInterval(() => {
            setActiveIdx(prev => {
                if (prev >= SYNC_AGENTS.length - 1) return prev;
                return prev + 1;
            });
        }, 1800);
        return () => clearInterval(interval);
    }, []);

    return (
        <div style={{
            position: 'fixed', inset: 0, background: 'rgba(15,23,42,0.7)',
            backdropFilter: 'blur(6px)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '24px',
        }} onClick={onClose}>
            <div
                style={{
                    background: '#ffffff', borderRadius: '28px', padding: '36px',
                    maxWidth: '560px', width: '100%',
                    boxShadow: '0 40px 80px rgba(0,0,0,0.25)',
                }}
                onClick={e => e.stopPropagation()}
            >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '28px' }}>
                    <div>
                        <p style={{ margin: '0 0 2px 0', fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#94a3b8' }}>Agentic Pipeline</p>
                        <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 900, color: '#0f172a', letterSpacing: '-0.01em' }}>Processing Emails…</h3>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: '#eef2ff', border: '1px solid #818cf8', padding: '5px 12px', borderRadius: '8px' }}>
                        <Loader2 size={12} style={{ color: '#4f46e5', animation: 'spin 1s linear infinite' }} />
                        <span style={{ fontSize: '9px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#4f46e5' }}>Live</span>
                    </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '28px' }}>
                    {SYNC_AGENTS.map((agent, i) => {
                        const Icon = agent.icon;
                        const isDone = i < activeIdx;
                        const isActive = i === activeIdx;
                        return (
                            <div key={agent.id} style={{
                                display: 'flex', alignItems: 'center', gap: '14px',
                                padding: '14px 16px', borderRadius: '14px',
                                background: isActive ? '#eef2ff' : isDone ? '#f0fdf4' : '#f8fafc',
                                border: `1.5px solid ${isActive ? '#818cf8' : isDone ? '#86efac' : '#e2e8f0'}`,
                                transition: 'all 0.4s ease',
                            }}>
                                <div style={{
                                    width: '36px', height: '36px', borderRadius: '10px', flexShrink: 0,
                                    background: isActive ? '#4f46e5' : isDone ? '#dcfce7' : '#f1f5f9',
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    {isActive
                                        ? <Loader2 size={18} style={{ color: '#fff', animation: 'spin 1s linear infinite' }} />
                                        : <Icon size={18} style={{ color: isDone ? '#15803d' : '#cbd5e1' }} />
                                    }
                                </div>
                                <div style={{ flex: 1 }}>
                                    <p style={{ margin: 0, fontWeight: 800, fontSize: '13px', color: isActive ? '#3730a3' : isDone ? '#15803d' : '#94a3b8' }}>
                                        {agent.name}
                                    </p>
                                    <p style={{ margin: '2px 0 0 0', fontSize: '11px', color: '#94a3b8', fontWeight: 500 }}>
                                        {isActive ? 'Running…' : isDone ? 'Completed' : 'Queued'}
                                    </p>
                                </div>
                                {isDone && <CheckCircle2 size={18} style={{ color: '#22c55e', flexShrink: 0 }} />}
                            </div>
                        );
                    })}
                </div>

                <div style={{ height: '3px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden' }}>
                    <div style={{
                        height: '100%', background: 'linear-gradient(90deg, #4f46e5, #818cf8)',
                        borderRadius: '999px',
                        width: `${(activeIdx / (SYNC_AGENTS.length - 1)) * 100}%`,
                        transition: 'width 0.6s ease',
                        boxShadow: '0 0 8px rgba(79,70,229,0.5)',
                    }} />
                </div>
            </div>
        </div>
    );
}


export default function CaseListPage() {
    const { instance, accounts } = useMsal();
    const navigate = useNavigate();
    const apiClient = createApiClient(instance);

    const [cases, setCases] = useState<Case[]>([]);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [category, setCategory] = useState('');
    const [status, setStatus] = useState('');
    const [sortBy, setSortBy] = useState('created_at');
    const [sortOrder, setSortOrder] = useState<'ASC' | 'DESC'>('DESC');

    // Stats
    const [stats, setStats] = useState<{ total_cases: number; pending_human_review: number; by_status: Record<string, number>; by_category: Record<string, number> } | null>(null);

    const fetchCases = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const params: ListCasesParams = {
                page, page_size: 50, sort_by: sortBy, sort_order: sortOrder,
                ...(search ? { search } : {}),
                ...(category ? { category } : {}),
                ...(status ? { status } : {}),
            };
            const data = await casesApi.listCases(apiClient, params);
            setCases(data.cases);
            setTotal(data.total);
            setTotalPages(data.total_pages);
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to load cases.');
        } finally {
            setLoading(false);
        }
    }, [page, search, category, status, sortBy, sortOrder]);

    const fetchStats = useCallback(async () => {
        try {
            const data = await casesApi.getStats(apiClient);
            setStats(data);
        } catch { /* ignore */ }
    }, []);

    const [isSyncing, setIsSyncing] = useState(false);
    const [showSyncModal, setShowSyncModal] = useState(false);
    const [syncMessage, setSyncMessage] = useState<string | null>(null);

    const handleSync = async () => {
        setIsSyncing(true);
        setShowSyncModal(true);
        setError(null);
        setSyncMessage(null);
        try {
            const response = await apiClient.post('/cases/sync');
            const data = response.data;
            setSyncMessage(data.message);

            let prevTotal = -1;
            let stableCount = 0;
            while (stableCount < 2) {
                await new Promise(resolve => setTimeout(resolve, 2000));
                const result = await casesApi.listCases(apiClient, {
                    page, page_size: 50, sort_by: sortBy, sort_order: sortOrder,
                    ...(search ? { search } : {}),
                    ...(category ? { category } : {}),
                    ...(status ? { status } : {}),
                });
                setCases(result.cases);
                setTotal(result.total);
                setTotalPages(result.total_pages);
                const hasProcessing = result.cases.some(c => c.status === 'RECEIVED' || c.status === 'PROCESSING');
                if (result.total === prevTotal && !hasProcessing) stableCount++;
                else { stableCount = 0; prevTotal = result.total; }
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to sync emails.');
        } finally {
            setIsSyncing(false);
            setShowSyncModal(false);
            setTimeout(() => setSyncMessage(null), 6000);
            fetchStats();
        }
    };

    useEffect(() => { fetchCases(); }, [fetchCases]);
    useEffect(() => { fetchStats(); }, [fetchStats]);

    const handleSort = (col: string) => {
        if (sortBy === col) setSortOrder(o => o === 'ASC' ? 'DESC' : 'ASC');
        else { setSortBy(col); setSortOrder('DESC'); }
    };

    const SortIcon = ({ col }: { col: string }) => (
        sortBy === col
            ? sortOrder === 'DESC' ? <ChevronDown className="w-3 h-3 ml-1 inline" /> : <ChevronUp className="w-3 h-3 ml-1 inline" />
            : null
    );

    const userName = DEV_BYPASS_AUTH ? 'Dev Mode' : (accounts[0]?.name || accounts[0]?.username || '');
    const initials = userName.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase() || 'U';

    const processed = stats?.by_status?.['PROCESSED'] ?? 0;
    const pendingReview = stats?.pending_human_review ?? 0;
    const processedPct = stats?.total_cases ? Math.round((processed / stats.total_cases) * 100) : 0;

    return (
        <div style={{ minHeight: '100vh', background: '#f8fafc' }}>

            {/* ── Glassmorphism sticky header ── */}
            <header style={{
                background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(12px)',
                borderBottom: '1px solid rgba(226,232,240,0.8)',
                padding: '0 32px', position: 'sticky', top: 0, zIndex: 50,
            }}>
                <div style={{ maxWidth: '1600px', margin: '0 auto', display: 'flex', alignItems: 'center', height: '64px', gap: '24px' }}>
                    {/* Logo */}
                    <img src="/assets/iat-logo.png" alt="IAT Insurance Group" style={{ height: '36px', width: 'auto', objectFit: 'contain' }} />
                    <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />

                    {/* Page title */}
                    <div style={{ flex: 1 }}>
                        <span style={{ color: '#0f172a', fontSize: '15px', fontWeight: 800, letterSpacing: '-0.01em' }}>
                            Case Management
                        </span>
                        <span style={{ color: '#94a3b8', fontSize: '13px', fontWeight: 500, marginLeft: '8px' }}>
                            · {total.toLocaleString()} cases
                        </span>
                    </div>

                    {/* Right */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        {/* Sync button */}
                        <button
                            onClick={handleSync}
                            disabled={isSyncing}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '8px',
                                background: isSyncing ? '#eef2ff' : '#4f46e5',
                                color: isSyncing ? '#4f46e5' : '#ffffff',
                                border: `1.5px solid ${isSyncing ? '#818cf8' : '#4f46e5'}`,
                                borderRadius: '12px', padding: '8px 18px',
                                fontSize: '13px', fontWeight: 700, cursor: isSyncing ? 'not-allowed' : 'pointer',
                                transition: 'all 0.2s',
                            }}
                            onMouseEnter={e => { if (!isSyncing) e.currentTarget.style.background = '#4338ca'; }}
                            onMouseLeave={e => { if (!isSyncing) e.currentTarget.style.background = '#4f46e5'; }}
                        >
                            {isSyncing
                                ? <><Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />Syncing…</>
                                : <><RefreshCw size={15} />Sync Emails</>
                            }
                        </button>

                        {/* Refresh */}
                        <button
                            onClick={fetchCases}
                            disabled={loading || isSyncing}
                            style={{
                                background: '#ffffff', border: '1.5px solid #e2e8f0',
                                borderRadius: '12px', padding: '8px', cursor: 'pointer',
                                color: '#4f46e5', display: 'flex',
                            }}
                        >
                            <RefreshCw size={16} className={loading && !isSyncing ? 'animate-spin' : ''} />
                        </button>

                        <div style={{ width: '1px', height: '24px', background: '#e2e8f0' }} />

                        {/* User info */}
                        <div style={{ textAlign: 'right' }}>
                            <p style={{ margin: 0, fontSize: '13px', fontWeight: 700, color: '#0f172a', lineHeight: 1 }}>{userName || 'Developer'}</p>
                            <p style={{ margin: '3px 0 0 0', fontSize: '10px', color: '#4f46e5', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                Underwriter
                            </p>
                        </div>
                        <div style={{
                            width: '38px', height: '38px', borderRadius: '12px',
                            background: 'linear-gradient(135deg, #4f46e5, #3730a3)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            boxShadow: '0 4px 12px rgba(79,70,229,0.3)',
                        }}>
                            <span style={{ color: '#ffffff', fontWeight: 900, fontSize: '13px' }}>{initials}</span>
                        </div>
                        {!DEV_BYPASS_AUTH && (
                            <button
                                onClick={() => instance.logoutRedirect()}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#64748b', background: 'none', border: '1.5px solid #e2e8f0', borderRadius: '10px', padding: '6px 12px', fontSize: '13px', fontWeight: 600, cursor: 'pointer' }}
                            >
                                <LogOut size={15} />
                            </button>
                        )}
                    </div>
                </div>
            </header>

            {/* ── Main content ── */}
            <main style={{ maxWidth: '1600px', margin: '0 auto', padding: '32px' }}>

                {/* Sync pipeline modal */}
                {showSyncModal && <SyncPipelineModal onClose={() => { }} />}

                {/* Sync success message */}
                {syncMessage && (
                    <div style={{
                        marginBottom: '24px', background: 'linear-gradient(135deg, #ecfdf5, #f0fdf4)',
                        border: '1.5px solid #86efac', borderRadius: '16px', padding: '14px 20px',
                        display: 'flex', alignItems: 'center', gap: '10px', color: '#14532d', fontSize: '13px', fontWeight: 600,
                    }}>
                        <CheckCircle2 size={18} style={{ color: '#22c55e', flexShrink: 0 }} />
                        {syncMessage}
                    </div>
                )}

                {/* ── Stats row ── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '28px' }}>
                    <StatCard title="Total Cases" value={stats?.total_cases ?? '—'} icon={Activity} accent="indigo" />
                    <StatCard title="Processed" value={processed} icon={CheckCircle2} accent="emerald" trend={processedPct ? `${processedPct}% of total` : undefined} trendPositive />
                    <StatCard title="Pending Review" value={pendingReview} icon={Clock} accent="amber" />
                    <StatCard title="Categories" value={Object.keys(stats?.by_category ?? {}).length} icon={Users} accent="indigo" />
                </div>

                {/* ── Filter bar ── */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '20px', alignItems: 'center' }}>
                    {/* Search */}
                    <div style={{ position: 'relative', flex: 1, minWidth: '220px', maxWidth: '380px' }}>
                        <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '15px', height: '15px', color: '#94a3b8' }} />
                        <input
                            type="text"
                            placeholder="Search Case ID, sender, subject…"
                            value={search}
                            onChange={e => { setSearch(e.target.value); setPage(1); }}
                            style={{
                                width: '100%', background: '#ffffff', border: '1.5px solid #e2e8f0',
                                borderRadius: '12px', padding: '9px 12px 9px 36px', fontSize: '13px',
                                color: '#0f172a', outline: 'none', fontWeight: 500,
                            }}
                        />
                    </div>

                    <select
                        value={category}
                        onChange={e => { setCategory(e.target.value); setPage(1); }}
                        style={{ background: '#ffffff', border: '1.5px solid #e2e8f0', borderRadius: '12px', padding: '9px 14px', fontSize: '13px', color: '#0f172a', cursor: 'pointer', fontWeight: 500 }}
                    >
                        <option value="">All Categories</option>
                        {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>

                    <select
                        value={status}
                        onChange={e => { setStatus(e.target.value); setPage(1); }}
                        style={{ background: '#ffffff', border: '1.5px solid #e2e8f0', borderRadius: '12px', padding: '9px 14px', fontSize: '13px', color: '#0f172a', cursor: 'pointer', fontWeight: 500 }}
                    >
                        <option value="">All Statuses</option>
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>

                {/* Error */}
                {error && (
                    <div style={{ marginBottom: '16px', background: '#fff1f2', border: '1.5px solid #fda4af', borderRadius: '14px', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#be123c', fontSize: '13px', fontWeight: 600 }}>
                        <span>{error}</span>
                        <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#be123c' }}>
                            <X size={15} />
                        </button>
                    </div>
                )}

                {/* ── Table ── */}
                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '24px', overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,0.04)' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid #f1f5f9', background: 'rgba(248,250,252,0.7)' }}>
                                    {[
                                        { key: 'case_id', label: 'Case ID' },
                                        { key: 'subject', label: 'Subject' },
                                        { key: 'sender', label: 'Sender' },
                                        { key: 'classification_category', label: 'Category' },
                                        { key: 'confidence_score', label: 'Confidence' },
                                        { key: 'status', label: 'Status' },
                                        { key: 'created_at', label: 'Received' },
                                        { key: 'updated_at', label: 'Updated' },
                                    ].map(col => (
                                        <th
                                            key={col.key}
                                            onClick={() => handleSort(col.key)}
                                            style={{
                                                padding: '12px 16px', textAlign: 'left',
                                                fontSize: '9px', fontWeight: 800, color: '#94a3b8',
                                                textTransform: 'uppercase', letterSpacing: '0.1em',
                                                cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none',
                                            }}
                                        >
                                            {col.label}<SortIcon col={col.key} />
                                        </th>
                                    ))}
                                    <th style={{ padding: '12px 16px', textAlign: 'right', fontSize: '9px', fontWeight: 800, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && !cases.length ? (
                                    Array.from({ length: 8 }).map((_, i) => (
                                        <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                                            {Array.from({ length: 9 }).map((_, j) => (
                                                <td key={j} style={{ padding: '16px' }}>
                                                    <div style={{ height: '13px', background: '#f1f5f9', borderRadius: '6px', width: `${60 + Math.random() * 40}px`, animation: 'pulse 1.5s infinite' }} />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : cases.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} style={{ padding: '64px 16px', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
                                            No cases found matching your criteria.
                                        </td>
                                    </tr>
                                ) : (
                                    cases.map(c => {
                                        const st = STATUS_STYLES[c.status] ?? { bg: '#f8fafc', border: '#e2e8f0', color: '#64748b', label: c.status };
                                        const cat = CATEGORY_STYLES[c.classification_category ?? ''] ?? { bg: '#f8fafc', border: '#e2e8f0', color: '#64748b' };
                                        const confidencePct = c.confidence_score != null
                                            ? (c.confidence_score <= 1 ? Math.round(c.confidence_score * 100) : Math.round(c.confidence_score))
                                            : null;

                                        return (
                                            <tr
                                                key={c.case_id}
                                                onClick={() => navigate(`/cases/${c.case_id}`)}
                                                style={{ borderBottom: '1px solid #f8fafc', cursor: 'pointer', transition: 'background 0.15s' }}
                                                onMouseEnter={e => (e.currentTarget.style.background = '#fafbff')}
                                                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                            >
                                                {/* Case ID */}
                                                <td style={{ padding: '14px 16px' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        {c.requires_human_review && <AlertTriangle size={13} style={{ color: '#f59e0b', flexShrink: 0 }} />}
                                                        <span style={{ color: '#4f46e5', fontFamily: 'monospace', fontSize: '12px', fontWeight: 700 }}>{c.case_id}</span>
                                                    </div>
                                                </td>

                                                {/* Subject */}
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{ color: '#0f172a', fontSize: '13px', fontWeight: 600, display: 'block', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.subject}>
                                                        {c.subject || '(No subject)'}
                                                    </span>
                                                </td>

                                                {/* Sender */}
                                                <td style={{ padding: '14px 16px', color: '#64748b', fontSize: '12px', maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500 }}>{c.sender}</td>

                                                {/* Category badge */}
                                                <td style={{ padding: '14px 16px' }}>
                                                    {c.classification_category ? (
                                                        <span style={{
                                                            display: 'inline-block', padding: '3px 10px', borderRadius: '8px',
                                                            background: cat.bg, border: `1px solid ${cat.border}`,
                                                            color: cat.color, fontSize: '10px', fontWeight: 800,
                                                            textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
                                                        }}>
                                                            {c.classification_category}
                                                        </span>
                                                    ) : <span style={{ color: '#cbd5e1', fontSize: '12px' }}>—</span>}
                                                </td>

                                                {/* Confidence bar */}
                                                <td style={{ padding: '14px 16px', minWidth: '100px' }}>
                                                    {confidencePct != null ? (
                                                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                            <span style={{ fontSize: '10px', fontWeight: 900, color: '#0f172a' }}>{confidencePct}%</span>
                                                            <div style={{ height: '4px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden', width: '64px' }}>
                                                                <div style={{
                                                                    height: '100%', borderRadius: '999px',
                                                                    background: confidencePct >= 75 ? '#22c55e' : '#f59e0b',
                                                                    width: `${confidencePct}%`,
                                                                    boxShadow: confidencePct >= 75 ? '0 0 6px rgba(34,197,94,0.4)' : '0 0 6px rgba(245,158,11,0.4)',
                                                                }} />
                                                            </div>
                                                        </div>
                                                    ) : <span style={{ color: '#cbd5e1', fontSize: '12px' }}>—</span>}
                                                </td>

                                                {/* Status pill */}
                                                <td style={{ padding: '14px 16px' }}>
                                                    <span style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '5px',
                                                        padding: '4px 10px', borderRadius: '999px',
                                                        background: st.bg, border: `1px solid ${st.border}`,
                                                        color: st.color, fontSize: '9px', fontWeight: 800,
                                                        textTransform: 'uppercase', letterSpacing: '0.08em', whiteSpace: 'nowrap',
                                                    }}>
                                                        {['PROCESSING', 'RECEIVED'].includes(c.status) && (
                                                            <Zap size={10} style={{ animation: 'pulse 1.5s ease-in-out infinite' }} />
                                                        )}
                                                        {st.label}
                                                    </span>
                                                </td>

                                                {/* Received */}
                                                <td style={{ padding: '14px 16px', color: '#94a3b8', fontSize: '12px', whiteSpace: 'nowrap', fontWeight: 500 }}>
                                                    {format(new Date(c.created_at), 'dd MMM yyyy HH:mm')}
                                                </td>

                                                {/* Updated */}
                                                <td style={{ padding: '14px 16px', color: '#94a3b8', fontSize: '12px', whiteSpace: 'nowrap', fontWeight: 500 }}>
                                                    {format(new Date(c.updated_at), 'dd MMM yyyy HH:mm')}
                                                </td>

                                                {/* Action */}
                                                <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                                                    <button
                                                        onClick={e => { e.stopPropagation(); navigate(`/cases/${c.case_id}`); }}
                                                        style={{
                                                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                                                            padding: '5px 12px', borderRadius: '8px',
                                                            background: '#eef2ff', border: '1px solid #c7d2fe',
                                                            color: '#4338ca', fontSize: '11px', fontWeight: 700,
                                                            cursor: 'pointer',
                                                        }}
                                                    >
                                                        View <ChevronRight size={13} />
                                                    </button>
                                                </td>
                                            </tr>
                                        );
                                    })
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div style={{ padding: '14px 20px', borderTop: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ color: '#94a3b8', fontSize: '12px', fontWeight: 600 }}>Page {page} of {totalPages}</span>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <button
                                    disabled={page === 1}
                                    onClick={() => setPage(p => p - 1)}
                                    style={{ padding: '6px 16px', background: '#ffffff', border: '1.5px solid #e2e8f0', color: '#0f172a', fontSize: '13px', fontWeight: 600, borderRadius: '10px', cursor: page === 1 ? 'not-allowed' : 'pointer', opacity: page === 1 ? 0.4 : 1 }}
                                >Previous</button>
                                <button
                                    disabled={page === totalPages}
                                    onClick={() => setPage(p => p + 1)}
                                    style={{ padding: '6px 16px', background: '#4f46e5', border: '1.5px solid #4f46e5', color: '#fff', fontSize: '13px', fontWeight: 600, borderRadius: '10px', cursor: page === totalPages ? 'not-allowed' : 'pointer', opacity: page === totalPages ? 0.5 : 1 }}
                                >Next</button>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
