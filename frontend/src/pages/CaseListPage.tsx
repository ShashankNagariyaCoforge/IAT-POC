import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import {
    Search, AlertTriangle, ChevronUp, ChevronDown, LogOut, RefreshCw, X,
    CheckCircle2, Clock, Zap, AlertCircle, ExternalLink, Activity, Trash2
} from 'lucide-react';
import { createApiClient, casesApi, ListCasesParams } from '../api/casesApi';
import type { Case, ClassificationCategory, CaseStatus } from '../types';
import { StatCard } from '../components/StatCard';
import { Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts';
import { SankeyChart } from '../components/SankeyChart';

const CATEGORIES: ClassificationCategory[] = [
    'New', 'Renewal', 'Query/General', 'Follow-up',
    'Complaint/Escalation', 'Regulatory/Legal', 'Documentation/Evidence', 'Spam/Irrelevant',
    'BOR',
];
const STATUSES: CaseStatus[] = ['RECEIVED', 'PROCESSING', 'CLASSIFIED', 'PENDING_REVIEW', 'PROCESSED', 'FAILED', 'BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY', 'UPDATED'];

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';
const POLL_INTERVAL_MS = parseInt(import.meta.env.VITE_DASHBOARD_POLL_INTERVAL_MS || '30000', 10);

export default function CaseListPage() {
    const { instance, accounts } = useMsal();
    const navigate = useNavigate();
    const apiClient = useMemo(() => createApiClient(instance), [instance]);

    const [cases, setCases] = useState<Case[]>([]);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [page, setPage] = useState(1);
    const [search, setSearch] = useState('');
    const [category, setCategory] = useState('');
    const [status, setStatus] = useState('');
    const [sortBy, setSortBy] = useState('updated_at');
    const [sortOrder, setSortOrder] = useState<'ASC' | 'DESC'>('DESC');

    // Stats & Dashboard
    const [dashboardMetrics, setDashboardMetrics] = useState<any>(null);

    // Selection State
    const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([]);
    const [deleting, setDeleting] = useState(false);

    const toggleSelect = (caseId: string) => {
        setSelectedCaseIds(prev =>
            prev.includes(caseId) ? prev.filter(id => id !== caseId) : [...prev, caseId]
        );
    };

    const toggleSelectAll = () => {
        if (selectedCaseIds.length === cases.length && cases.length > 0) {
            setSelectedCaseIds([]);
        } else {
            setSelectedCaseIds(cases.map(c => c.case_id));
        }
    };

    const handleBulkDelete = async () => {
        if (selectedCaseIds.length === 0) return;
        if (!window.confirm(`Are you sure you want to delete ${selectedCaseIds.length} cases? This action cannot be undone.`)) return;

        setDeleting(true);
        try {
            await casesApi.deleteCases(apiClient, selectedCaseIds);
            setSelectedCaseIds([]);
            fetchCases();
            fetchDashboardMetrics();
        } catch (err: any) {
            setError(err.response?.data?.detail || 'Failed to delete cases.');
        } finally {
            setDeleting(false);
        }
    };

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

    const fetchDashboardMetrics = useCallback(async () => {
        try {
            const data = await casesApi.getDashboardMetrics(apiClient);
            setDashboardMetrics(data);
        } catch { /* ignore */ }
    }, [apiClient]);



    // Use refs to avoid stale closures in the interval
    const fetchCasesRef = useRef(fetchCases);
    const fetchDashboardMetricsRef = useRef(fetchDashboardMetrics);

    useEffect(() => {
        fetchCasesRef.current = fetchCases;
        fetchDashboardMetricsRef.current = fetchDashboardMetrics;
    }, [fetchCases, fetchDashboardMetrics]);

    // Initial fetch and dependency-driven fetch
    useEffect(() => {
        fetchCases();
        fetchDashboardMetrics();
    }, [fetchCases, fetchDashboardMetrics]);

    // Background auto-polling (runs exactly once, uses refs for latest state)
    useEffect(() => {
        if (POLL_INTERVAL_MS <= 0) return;

        const intervalId = setInterval(() => {
            fetchCasesRef.current();
            fetchDashboardMetricsRef.current();
        }, POLL_INTERVAL_MS);

        return () => clearInterval(intervalId);
    }, []); // Empty dependency array ensures this effect runs exactly once and the timer never gets cleared prematurely

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
                        {/* Refresh */}
                        <button
                            onClick={fetchCases}
                            disabled={loading}
                            style={{
                                background: '#ffffff', border: '1.5px solid #e2e8f0',
                                borderRadius: '12px', padding: '8px', cursor: 'pointer',
                                color: '#4f46e5', display: 'flex',
                            }}
                        >
                            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
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



                {/* Welcome section */}
                <div style={{ marginBottom: '32px' }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', background: '#eef2ff', color: '#4338ca', padding: '6px 12px', borderRadius: '999px', fontSize: '10px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '16px' }}>
                        <Zap size={12} /> Agentic Efficiency Live
                    </div>
                    <h1 style={{ fontSize: '32px', fontWeight: 900, color: '#0f172a', margin: '0 0 8px 0', letterSpacing: '-0.02em' }}>
                        Underwriting Workbench
                    </h1>
                    <p style={{ margin: 0, fontSize: '16px', color: '#64748b', fontWeight: 500 }}>
                        Streamlined agent operations for your current intake.
                    </p>
                </div>

                {/* ── Top Metrics Row ── */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '20px', marginBottom: '32px' }}>
                    <StatCard
                        title="Decision Accuracy"
                        value={dashboardMetrics?.decision_accuracy ? `${(dashboardMetrics.decision_accuracy * 100).toFixed(1)}%` : '—'}
                        icon={Zap} accent="indigo"
                    />
                    <StatCard
                        title="Avg. Triage Time"
                        value={dashboardMetrics?.avg_agent_processing_time_ms ? `${(dashboardMetrics.avg_agent_processing_time_ms / 1000).toFixed(2)}s` : '—'}
                        icon={Clock} accent="indigo"
                    />
                    <StatCard
                        title="Extraction Accuracy"
                        value={dashboardMetrics?.extraction_accuracy ? `${(dashboardMetrics.extraction_accuracy * 100).toFixed(1)}%` : '—'}
                        icon={CheckCircle2} accent="emerald"
                    />
                    <StatCard
                        title="Review Required"
                        value={dashboardMetrics?.action_required_threads ?? '—'}
                        icon={AlertCircle} accent="amber"
                    />
                </div>

                {/* ── Charts Row ── */}
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px', marginBottom: '32px' }}>
                    {/* Sankey Chart */}
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '32px', borderRadius: '24px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.02)' }}>
                        <div style={{ marginBottom: '24px' }}>
                            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0' }}>Pipeline Efficiency</h3>
                            <p style={{ margin: 0, fontSize: '13px', color: '#64748b', fontWeight: 500 }}>Recommended vs Corrupted throughput</p>
                        </div>
                        <div style={{ height: '350px' }}>
                            {dashboardMetrics?.sankey_chart && <SankeyChart data={dashboardMetrics.sankey_chart} />}
                        </div>
                    </div>

                    {/* Pie Chart */}
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', padding: '32px', borderRadius: '24px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.02)', display: 'flex', flexDirection: 'column' }}>
                        <div style={{ marginBottom: '16px' }}>
                            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0' }}>Pipeline Status Triage</h3>
                            <p style={{ margin: 0, fontSize: '13px', color: '#64748b', fontWeight: 500 }}>Status categorization of current load</p>
                        </div>
                        <div style={{ flex: 1, minHeight: '200px' }}>
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie
                                        data={dashboardMetrics?.pie_chart || []}
                                        cx="50%" cy="50%" innerRadius={60} outerRadius={85} paddingAngle={5}
                                        dataKey="value"
                                    >
                                        {(dashboardMetrics?.pie_chart || []).map((entry: any, index: number) => (
                                            <Cell key={`cell-${index}`} fill={entry.color} stroke="none" />
                                        ))}
                                    </Pie>
                                    <Tooltip contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)' }} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {(dashboardMetrics?.pie_chart || []).map((item: any) => (
                                <div key={item.name} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px', borderRadius: '8px', background: '#f8fafc' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: item.color }} />
                                        <span style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: '#475569' }}>{item.name}</span>
                                    </div>
                                    <span style={{ fontSize: '13px', fontWeight: 900, color: '#0f172a' }}>{item.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                    <div>
                        <h3 style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', margin: '0 0 4px 0', letterSpacing: '-0.01em' }}>Active Agent Pipeline</h3>
                        <p style={{ margin: 0, fontSize: '13px', color: '#64748b', fontWeight: 500 }}>Real-time status of automated extractions and validation loops.</p>
                    </div>

                    {/* ── Filter bar ── */}
                    <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                        <div style={{ position: 'relative', minWidth: '220px' }}>
                            <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: '15px', height: '15px', color: '#94a3b8' }} />
                            <input
                                type="text"
                                placeholder="Search Case ID..."
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
                                    <th style={{ padding: '20px 16px', width: '48px' }}>
                                        <input
                                            type="checkbox"
                                            checked={cases.length > 0 && selectedCaseIds.length === cases.length}
                                            onChange={toggleSelectAll}
                                            style={{
                                                width: '18px', height: '18px', borderRadius: '6px',
                                                border: '2px solid #cbd5e1', cursor: 'pointer',
                                                accentColor: '#4f46e5'
                                            }}
                                        />
                                    </th>
                                    {[
                                        { key: 'case_id', label: 'Submission ID' },
                                        { key: 'sender', label: 'Broker Entity' },
                                        { key: 'classification_category', label: 'Product Line' },
                                        { key: 'confidence_score', label: 'Confidence' },
                                        { key: 'status', label: 'Status' },
                                        { key: 'updated_at', label: 'Last Activity' },
                                    ].map(col => (
                                        <th
                                            key={col.key}
                                            onClick={() => handleSort(col.key)}
                                            style={{
                                                padding: '20px 16px', textAlign: col.key === 'confidence_score' ? 'center' : 'left',
                                                fontSize: '10px', fontWeight: 900, color: '#94a3b8',
                                                textTransform: 'uppercase', letterSpacing: '0.1em',
                                                cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none',
                                            }}
                                        >
                                            {col.label}<SortIcon col={col.key} />
                                        </th>
                                    ))}
                                    <th style={{ padding: '20px 16px', textAlign: 'left', fontSize: '10px', fontWeight: 900, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && !cases.length ? (
                                    Array.from({ length: 8 }).map((_, i) => (
                                        <tr key={i} style={{ borderBottom: '1px solid #f8fafc' }}>
                                            <td style={{ padding: '16px' }}>
                                                <div style={{ width: '18px', height: '18px', background: '#f1f5f9', borderRadius: '4px', animation: 'pulse 1.5s infinite' }} />
                                            </td>
                                            {Array.from({ length: 6 }).map((_, j) => (
                                                <td key={j} style={{ padding: '16px' }}>
                                                    <div style={{ height: '13px', background: '#f1f5f9', borderRadius: '6px', width: `${60 + Math.random() * 40}px`, animation: 'pulse 1.5s infinite' }} />
                                                </td>
                                            ))}
                                            <td style={{ padding: '16px' }}>
                                                <div style={{ height: '13px', background: '#f1f5f9', borderRadius: '6px', width: '80px', animation: 'pulse 1.5s infinite' }} />
                                            </td>
                                        </tr>
                                    ))
                                ) : cases.length === 0 ? (
                                    <tr>
                                        <td colSpan={8} style={{ padding: '64px 16px', textAlign: 'center', color: '#94a3b8', fontSize: '14px' }}>
                                            No cases found matching your criteria.
                                        </td>
                                    </tr>
                                ) : (
                                    cases.map(c => {
                                        const confidencePct = c.confidence_score != null
                                            ? (c.confidence_score <= 1 ? Math.round(c.confidence_score * 100) : Math.round(c.confidence_score))
                                            : null;
                                        const isSelected = selectedCaseIds.includes(c.case_id);

                                        return (
                                            <tr
                                                key={c.case_id}
                                                onClick={() => navigate(`/cases/${c.case_id}`)}
                                                style={{ borderBottom: '1px solid #f8fafc', cursor: 'pointer', transition: 'background 0.15s', background: isSelected ? 'rgba(79, 70, 229, 0.04)' : 'transparent' }}
                                                onMouseEnter={e => (e.currentTarget.style.background = isSelected ? 'rgba(79, 70, 229, 0.08)' : '#fafbff')}
                                                onMouseLeave={e => (e.currentTarget.style.background = isSelected ? 'rgba(79, 70, 229, 0.04)' : 'transparent')}
                                            >
                                                {/* Checkbox */}
                                                <td style={{ padding: '24px 16px' }} onClick={e => e.stopPropagation()}>
                                                    <input
                                                        type="checkbox"
                                                        checked={isSelected}
                                                        onChange={() => toggleSelect(c.case_id)}
                                                        style={{
                                                            width: '18px', height: '18px', borderRadius: '6px',
                                                            border: '2px solid #cbd5e1', cursor: 'pointer',
                                                            accentColor: '#4f46e5'
                                                        }}
                                                    />
                                                </td>

                                                {/* Case ID */}
                                                <td style={{ padding: '24px 16px' }}>
                                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                        {c.requires_human_review && <AlertTriangle size={13} style={{ color: '#f59e0b', flexShrink: 0 }} />}
                                                        <span style={{ color: '#4f46e5', fontFamily: 'monospace', fontSize: '14px', fontWeight: 800, letterSpacing: '-0.05em' }}>{c.case_id}</span>
                                                    </div>
                                                </td>

                                                {/* Sender */}
                                                <td style={{ padding: '24px 16px', color: '#1e293b', fontSize: '14px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 800 }}>{c.sender}</td>

                                                {/* Category */}
                                                <td style={{ padding: '24px 16px' }}>
                                                    <span style={{ color: '#475569', fontSize: '14px', fontWeight: 500 }}>
                                                        {c.classification_category || '—'}
                                                    </span>
                                                </td>

                                                {/* Confidence bar */}
                                                <td style={{ padding: '24px 16px', minWidth: '120px' }}>
                                                    {confidencePct != null ? (
                                                        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
                                                            <span style={{ fontSize: '10px', fontWeight: 900, color: '#0f172a' }}>{confidencePct}%</span>
                                                            <div style={{ height: '6px', background: '#f1f5f9', borderRadius: '999px', overflow: 'hidden', width: '96px' }}>
                                                                <div style={{
                                                                    height: '100%', borderRadius: '999px',
                                                                    transition: 'all 0.7s ease',
                                                                    background: confidencePct >= 90 ? '#10b981' : '#f59e0b',
                                                                    width: `${confidencePct}%`,
                                                                    boxShadow: confidencePct >= 90 ? '0 0 8px rgba(16,185,129,0.3)' : '0 0 8px rgba(245,158,11,0.3)',
                                                                }} />
                                                            </div>
                                                        </div>
                                                    ) : <span style={{ color: '#cbd5e1', fontSize: '12px', display: 'block', textAlign: 'center' }}>—</span>}
                                                </td>

                                                {/* Status pill */}
                                                <td style={{ padding: '24px 16px' }}>
                                                    <span style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '6px',
                                                        padding: '6px 12px', borderRadius: '999px',
                                                        background: c.status === 'PROCESSED' ? '#ecfdf5' : c.status === 'UPDATED' ? '#eef2ff' : c.status === 'PENDING_REVIEW' || c.status === 'NEEDS_REVIEW_SAFETY' ? '#e0f2fe' : '#fffbeb',
                                                        border: c.status === 'PROCESSED' ? '1px solid #d1fae5' : c.status === 'UPDATED' ? '1px solid #e0e7ff' : c.status === 'PENDING_REVIEW' || c.status === 'NEEDS_REVIEW_SAFETY' ? '1px solid #bae6fd' : '1px solid #fef3c7',
                                                        color: c.status === 'PROCESSED' ? '#047857' : c.status === 'UPDATED' ? '#4338ca' : c.status === 'PENDING_REVIEW' || c.status === 'NEEDS_REVIEW_SAFETY' ? '#0369a1' : '#b45309',
                                                        fontSize: '10px', fontWeight: 900,
                                                        textTransform: 'uppercase', letterSpacing: '-0.05em', whiteSpace: 'nowrap',
                                                    }}>
                                                        {c.status === 'PROCESSED' && <Zap size={10} />}
                                                        {c.status === 'UPDATED' && <Activity size={10} />}
                                                        {(c.status === 'PENDING_REVIEW' || c.status === 'NEEDS_REVIEW_SAFETY' || c.requires_human_review) && <AlertCircle size={10} />}
                                                        {c.status === 'UPDATED' ? 'NEW ACTIVITY' : c.status.replace('_', ' ')}
                                                    </span>
                                                </td>

                                                {/* Last Activity */}
                                                <td style={{ padding: '24px 16px' }}>
                                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                                        <span style={{ color: '#1e293b', fontSize: '13px', fontWeight: 700 }}>
                                                            {new Date(c.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
                                                        </span>
                                                        <span style={{ color: '#94a3b8', fontSize: '11px', fontWeight: 500 }}>
                                                            {new Date(c.updated_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                                                        </span>
                                                    </div>
                                                </td>

                                                {/* Action */}
                                                <td style={{ padding: '24px 16px', textAlign: 'left' }}>
                                                    <button
                                                        onClick={e => { e.stopPropagation(); navigate(`/cases/${c.case_id}`); }}
                                                        style={{
                                                            display: 'inline-flex', alignItems: 'center', gap: '6px',
                                                            padding: '6px 12px', borderRadius: '8px',
                                                            background: '#eef2ff', border: '1px solid #e0e7ff',
                                                            color: '#4f46e5', fontSize: '11px', fontWeight: 800,
                                                            cursor: 'pointer', whiteSpace: 'nowrap', transition: 'all 0.2s'
                                                        }}
                                                        onMouseEnter={e => { e.currentTarget.style.background = '#e0e7ff'; e.currentTarget.style.color = '#3730a3'; }}
                                                        onMouseLeave={e => { e.currentTarget.style.background = '#eef2ff'; e.currentTarget.style.color = '#4f46e5'; }}
                                                    >
                                                        <ExternalLink size={11} />
                                                        View PAS
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

            {/* ── Beautiful Delete Button ── */}
            {selectedCaseIds.length > 0 && (
                <div style={{
                    position: 'fixed', bottom: '40px', left: '50%', transform: 'translateX(-50%)',
                    zIndex: 100, animation: 'slideUp 0.3s ease-out'
                }}>
                    <button
                        onClick={handleBulkDelete}
                        disabled={deleting}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '10px',
                            padding: '14px 28px', borderRadius: '16px',
                            background: 'linear-gradient(135deg, #f43f5e, #e11d48)',
                            color: '#ffffff', fontWeight: 800, fontSize: '14px',
                            boxShadow: '0 10px 25px -5px rgba(225, 29, 72, 0.4)',
                            border: '1px solid rgba(255,255,255,0.2)',
                            cursor: 'pointer', transition: 'all 0.2s',
                            backdropFilter: 'blur(8px)',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.05)'; e.currentTarget.style.boxShadow = '0 15px 30px -5px rgba(225, 29, 72, 0.5)'; }}
                        onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 10px 25px -5px rgba(225, 29, 72, 0.4)'; }}
                    >
                        {deleting ? (
                            <RefreshCw size={18} className="animate-spin" />
                        ) : (
                            <Trash2 size={18} />
                        )}
                        <span>Delete {selectedCaseIds.length} Selected Cases</span>
                    </button>
                </div>
            )}

            <style>{`
                @keyframes slideUp {
                    from { transform: translate(-50%, 100px); opacity: 0; }
                    to { transform: translate(-50%, 0); opacity: 1; }
                }
            `}</style>
        </div>
    );
}
