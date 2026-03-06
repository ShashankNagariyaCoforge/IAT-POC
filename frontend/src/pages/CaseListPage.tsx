import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMsal } from '@azure/msal-react';
import { Search, AlertTriangle, ChevronUp, ChevronDown, LogOut, RefreshCw, X } from 'lucide-react';
import { createApiClient, casesApi, ListCasesParams } from '../api/casesApi';
import { StatusBadge } from '../components/StatusBadge';
import { CategoryBadge } from '../components/CategoryBadge';
import { ConfidenceMeter } from '../components/ConfidenceMeter';
import type { Case, ClassificationCategory, CaseStatus } from '../types';
import { format } from 'date-fns';

const CATEGORIES: ClassificationCategory[] = [
    'New', 'Renewal', 'Query/General', 'Follow-up',
    'Complaint/Escalation', 'Regulatory/Legal', 'Documentation/Evidence', 'Spam/Irrelevant',
];
const STATUSES: CaseStatus[] = ['RECEIVED', 'PROCESSING', 'CLASSIFIED', 'PENDING_REVIEW', 'PROCESSED', 'FAILED', 'BLOCKED_SAFETY', 'NEEDS_REVIEW_SAFETY'];

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

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

    const [isSyncing, setIsSyncing] = useState(false);
    const [syncMessage, setSyncMessage] = useState<string | null>(null);

    const handleSync = async () => {
        setIsSyncing(true);
        setError(null);
        setSyncMessage(null);
        try {
            // Fire sync request
            const response = await apiClient.post('/cases/sync');
            const data = response.data;
            setSyncMessage(data.message);

            // Keep polling until the case count has been stable for 2 checks (cases stopped loading)
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

                // Still processing if: new cases being added OR any case hasn't been classified yet
                const hasProcessingCases = result.cases.some(
                    c => c.status === 'RECEIVED' || c.status === 'PROCESSING'
                );

                if (result.total === prevTotal && !hasProcessingCases) {
                    stableCount++;
                } else {
                    stableCount = 0;
                    prevTotal = result.total;
                }
            }
        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'Failed to sync emails.');
        } finally {
            setIsSyncing(false);
            setTimeout(() => setSyncMessage(null), 5000);
        }
    };

    useEffect(() => { fetchCases(); }, [fetchCases]);

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

    return (
        <div style={{ minHeight: '100vh', background: '#F4F6F8' }}>

            {/* ── Single Header (IAT style: white bg, navy text) ── */}
            <header style={{ background: '#ffffff', borderBottom: '1px solid #D1D9E0', padding: '0 32px' }}>
                <div style={{ maxWidth: '1600px', margin: '0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: '64px' }}>
                    <img src="/assets/iat-logo.png" alt="IAT Insurance Group" style={{ height: '40px', width: 'auto', objectFit: 'contain' }} />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                        <span style={{ color: '#5a7184', fontSize: '14px' }}>{userName}</span>
                        {!DEV_BYPASS_AUTH && (
                            <button
                                onClick={() => instance.logoutRedirect()}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00467F', background: 'none', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '6px 12px', fontSize: '13px', fontWeight: 500, cursor: 'pointer' }}
                            >
                                <LogOut className="w-4 h-4" /> Sign out
                            </button>
                        )}
                    </div>
                </div>
            </header>

            {/* ── Page content ── */}
            <main style={{ maxWidth: '1600px', margin: '0 auto', padding: '32px', }}>

                {/* Title bar */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ color: '#00263E', fontSize: '22px', fontWeight: 700, margin: 0 }}>Case Management</h1>
                        <p style={{ color: '#8fa1b0', fontSize: '13px', margin: '4px 0 0 0' }}>{total.toLocaleString()} total cases</p>
                    </div>
                    <div style={{ display: 'flex', gap: '12px' }}>
                        <button
                            onClick={handleSync}
                            disabled={isSyncing}
                            style={{ background: '#00467F', border: 'none', borderRadius: '6px', padding: '8px 16px', cursor: isSyncing ? 'not-allowed' : 'pointer', color: '#fff', fontSize: '13px', fontWeight: 500, display: 'flex', alignItems: 'center', gap: '8px', opacity: isSyncing ? 0.7 : 1 }}
                        >
                            <RefreshCw className={`w-4 h-4 ${isSyncing ? 'animate-spin' : ''}`} />
                            {isSyncing ? 'Syncing...' : 'Sync New Emails'}
                        </button>
                        <button
                            onClick={fetchCases}
                            disabled={loading || isSyncing}
                            title="Refresh"
                            style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '8px', cursor: (loading || isSyncing) ? 'not-allowed' : 'pointer', color: '#00467F', display: 'flex' }}
                        >
                            <RefreshCw className={`w-4 h-4 ${loading && !isSyncing ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>

                {/* Success Message */}
                {syncMessage && (
                    <div style={{ marginBottom: '16px', background: '#ecfdf5', border: '1px solid #6ee7b7', borderRadius: '8px', padding: '12px 16px', color: '#065f46', fontSize: '13px', fontWeight: 500 }}>
                        {syncMessage}
                    </div>
                )}

                {/* Filters */}
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginBottom: '20px' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: '200px', maxWidth: '360px' }}>
                        <Search style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', width: '16px', height: '16px', color: '#8fa1b0' }} />
                        <input
                            type="text"
                            placeholder="Search Case ID, sender, subject…"
                            value={search}
                            onChange={e => { setSearch(e.target.value); setPage(1); }}
                            style={{
                                width: '100%', background: '#fff', border: '1px solid #D1D9E0', borderRadius: '6px',
                                padding: '8px 12px 8px 34px', fontSize: '13px', color: '#00263E', outline: 'none',
                            }}
                        />
                    </div>
                    <select
                        value={category}
                        onChange={e => { setCategory(e.target.value); setPage(1); }}
                        style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '8px 12px', fontSize: '13px', color: '#00263E', cursor: 'pointer' }}
                    >
                        <option value="">All Categories</option>
                        {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <select
                        value={status}
                        onChange={e => { setStatus(e.target.value); setPage(1); }}
                        style={{ background: '#fff', border: '1px solid #D1D9E0', borderRadius: '6px', padding: '8px 12px', fontSize: '13px', color: '#00263E', cursor: 'pointer' }}
                    >
                        <option value="">All Statuses</option>
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>

                {/* Error */}
                {error && (
                    <div style={{ marginBottom: '16px', background: '#fff5f5', border: '1px solid #fca5a5', borderRadius: '8px', padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: '#b91c1c', fontSize: '13px' }}>
                        <span>{error}</span>
                        <button onClick={() => setError(null)} style={{ marginLeft: '16px', background: 'none', border: 'none', cursor: 'pointer', color: '#b91c1c' }}>
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Table */}
                <div style={{ background: '#ffffff', border: '1px solid #D1D9E0', borderRadius: '8px', overflow: 'hidden', boxShadow: '0 2px 8px rgba(0,38,62,0.06)' }}>
                    <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '2px solid #D1D9E0', background: '#F4F6F8' }}>
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
                                            style={{ padding: '10px 16px', textAlign: 'left', fontSize: '11px', fontWeight: 600, color: '#00263E', textTransform: 'uppercase', letterSpacing: '0.05em', cursor: 'pointer', whiteSpace: 'nowrap', userSelect: 'none' }}
                                        >
                                            {col.label}<SortIcon col={col.key} />
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {loading && !cases.length ? (
                                    Array.from({ length: 8 }).map((_, i) => (
                                        <tr key={i} style={{ borderBottom: '1px solid #eef1f4' }}>
                                            {Array.from({ length: 9 }).map((_, j) => (
                                                <td key={j} style={{ padding: '14px 16px' }}>
                                                    <div style={{ height: '14px', background: '#eef1f4', borderRadius: '4px', width: '80px', animation: 'pulse 1.5s infinite' }} />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : cases.length === 0 ? (
                                    <tr>
                                        <td colSpan={8} style={{ padding: '48px 16px', textAlign: 'center', color: '#8fa1b0', fontSize: '14px' }}>
                                            No cases found matching your criteria.
                                        </td>
                                    </tr>
                                ) : (
                                    cases.map(c => (
                                        <tr
                                            key={c.case_id}
                                            onClick={() => navigate(`/cases/${c.case_id}`)}
                                            style={{ borderBottom: '1px solid #eef1f4', cursor: 'pointer', transition: 'background 0.15s' }}
                                            onMouseEnter={e => (e.currentTarget.style.background = '#f0f5fb')}
                                            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                        >
                                            <td style={{ padding: '12px 16px' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }} title={c.requires_human_review ? 'Human review required' : ''}>
                                                    {c.requires_human_review && (
                                                        <AlertTriangle className="w-3.5 h-3.5" style={{ color: '#f59e0b', flexShrink: 0 }} />
                                                    )}
                                                    <span style={{ color: '#00467F', fontFamily: 'monospace', fontSize: '13px', textDecoration: 'underline' }}>{c.case_id}</span>
                                                </div>
                                            </td>
                                            <td style={{ padding: '12px 16px' }}>
                                                <span style={{ color: '#00263E', fontSize: '13px', display: 'block', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={c.subject}>
                                                    {c.subject || '(No subject)'}
                                                </span>
                                            </td>
                                            <td style={{ padding: '12px 16px', color: '#5a7184', fontSize: '13px', maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.sender}</td>
                                            <td style={{ padding: '12px 16px' }}><CategoryBadge category={c.classification_category} /></td>
                                            <td style={{ padding: '12px 16px', minWidth: '100px' }}><ConfidenceMeter score={c.confidence_score} /></td>
                                            <td style={{ padding: '12px 16px' }}><StatusBadge status={c.status} /></td>
                                            <td style={{ padding: '12px 16px', color: '#8fa1b0', fontSize: '12px', whiteSpace: 'nowrap' }}>
                                                {format(new Date(c.created_at), 'dd MMM yyyy HH:mm')}
                                            </td>
                                            <td style={{ padding: '12px 16px', color: '#8fa1b0', fontSize: '12px', whiteSpace: 'nowrap' }}>
                                                {format(new Date(c.updated_at), 'dd MMM yyyy HH:mm')}
                                            </td>
                                        </tr>
                                    ))
                                )}
                            </tbody>
                        </table>
                    </div>

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div style={{ padding: '12px 16px', borderTop: '1px solid #D1D9E0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ color: '#8fa1b0', fontSize: '13px' }}>Page {page} of {totalPages}</span>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <button
                                    disabled={page === 1}
                                    onClick={() => setPage(p => p - 1)}
                                    style={{ padding: '6px 14px', background: '#fff', border: '1px solid #D1D9E0', color: '#00263E', fontSize: '13px', borderRadius: '6px', cursor: page === 1 ? 'not-allowed' : 'pointer', opacity: page === 1 ? 0.5 : 1 }}
                                >
                                    Previous
                                </button>
                                <button
                                    disabled={page === totalPages}
                                    onClick={() => setPage(p => p + 1)}
                                    style={{ padding: '6px 14px', background: '#00467F', border: '1px solid #00467F', color: '#fff', fontSize: '13px', borderRadius: '6px', cursor: page === totalPages ? 'not-allowed' : 'pointer', opacity: page === totalPages ? 0.5 : 1 }}
                                >
                                    Next
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            </main>
        </div>
    );
}
