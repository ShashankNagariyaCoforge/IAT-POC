import React, { useCallback, useEffect, useState } from 'react';
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
const STATUSES: CaseStatus[] = ['RECEIVED', 'PROCESSING', 'CLASSIFIED', 'PENDING_REVIEW', 'NOTIFIED', 'FAILED'];

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
        } catch (err: any) {
            setError(err.message || 'Failed to load cases.');
        } finally {
            setLoading(false);
        }
    }, [page, search, category, status, sortBy, sortOrder]);

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
        <div className="min-h-screen bg-slate-950">
            {/* Header */}
            <header className="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
                        <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                    </div>
                    <div>
                        <h1 className="text-white font-semibold text-sm">IAT Insurance</h1>
                        <p className="text-slate-400 text-xs">Email Automation Platform</p>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <span className="text-slate-400 text-sm">{userName}</span>
                    {!DEV_BYPASS_AUTH && (
                        <button
                            onClick={() => instance.logoutRedirect()}
                            className="flex items-center gap-2 text-slate-400 hover:text-white text-sm transition-colors"
                        >
                            <LogOut className="w-4 h-4" /> Sign out
                        </button>
                    )}
                </div>
            </header>

            <main className="max-w-screen-2xl mx-auto px-6 py-6">
                {/* Stats bar */}
                <div className="mb-6 flex items-center justify-between">
                    <div>
                        <h2 className="text-xl font-bold text-white">Cases</h2>
                        <p className="text-slate-400 text-sm mt-0.5">{total.toLocaleString()} total</p>
                    </div>
                    <button onClick={fetchCases} className="text-slate-400 hover:text-white transition-colors" title="Refresh">
                        <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                </div>

                {/* Filters */}
                <div className="flex flex-wrap gap-3 mb-5">
                    <div className="relative flex-1 min-w-[200px] max-w-sm">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                        <input
                            type="text"
                            placeholder="Search Case ID, sender, subject…"
                            value={search}
                            onChange={e => { setSearch(e.target.value); setPage(1); }}
                            className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-2 text-sm text-white
                         placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
                        />
                    </div>
                    <select
                        value={category}
                        onChange={e => { setCategory(e.target.value); setPage(1); }}
                        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white
                       focus:outline-none focus:border-blue-500 transition-colors"
                    >
                        <option value="">All Categories</option>
                        {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                    <select
                        value={status}
                        onChange={e => { setStatus(e.target.value); setPage(1); }}
                        className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white
                       focus:outline-none focus:border-blue-500 transition-colors"
                    >
                        <option value="">All Statuses</option>
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                </div>

                {/* Error */}
                {error && (
                    <div className="mb-4 bg-red-900/30 border border-red-700 rounded-lg px-4 py-3 flex items-center justify-between text-red-300 text-sm">
                        <span>{error}</span>
                        <button onClick={() => setError(null)} className="ml-4 text-red-400 hover:text-red-200 flex-shrink-0">
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                )}

                {/* Table */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                    <div className="overflow-x-auto">
                        <table className="w-full">
                            <thead>
                                <tr className="border-b border-slate-800">
                                    {[
                                        { key: 'case_id', label: 'Case ID' },
                                        { key: 'subject', label: 'Subject' },
                                        { key: 'sender', label: 'Sender' },
                                        { key: 'classification_category', label: 'Category' },
                                        { key: 'confidence_score', label: 'Confidence' },
                                        { key: 'status', label: 'Status' },
                                        { key: 'email_count', label: 'Emails' },
                                        { key: 'created_at', label: 'Received' },
                                        { key: 'updated_at', label: 'Updated' },
                                    ].map(col => (
                                        <th
                                            key={col.key}
                                            onClick={() => handleSort(col.key)}
                                            className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider
                                 cursor-pointer hover:text-white transition-colors select-none whitespace-nowrap"
                                        >
                                            {col.label}<SortIcon col={col.key} />
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {loading && !cases.length ? (
                                    Array.from({ length: 8 }).map((_, i) => (
                                        <tr key={i} className="border-b border-slate-800/50 animate-pulse">
                                            {Array.from({ length: 9 }).map((_, j) => (
                                                <td key={j} className="px-4 py-3.5">
                                                    <div className="h-4 bg-slate-800 rounded w-24" />
                                                </td>
                                            ))}
                                        </tr>
                                    ))
                                ) : cases.length === 0 ? (
                                    <tr>
                                        <td colSpan={9} className="px-4 py-12 text-center text-slate-500">
                                            No cases found matching your criteria.
                                        </td>
                                    </tr>
                                ) : (
                                    cases.map(c => (
                                        <tr
                                            key={c.case_id}
                                            onClick={() => navigate(`/cases/${c.case_id}`)}
                                            className="border-b border-slate-800/50 hover:bg-slate-800/40 cursor-pointer transition-colors"
                                        >
                                            <td className="px-4 py-3.5">
                                                <div className="flex items-center gap-1.5">
                                                    {c.requires_human_review && (
                                                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 flex-shrink-0" title="Human review required" />
                                                    )}
                                                    <span className="text-blue-400 font-mono text-sm hover:underline">{c.case_id}</span>
                                                </div>
                                            </td>
                                            <td className="px-4 py-3.5">
                                                <span className="text-slate-200 text-sm truncate max-w-[200px] block" title={c.subject}>
                                                    {c.subject || '(No subject)'}
                                                </span>
                                            </td>
                                            <td className="px-4 py-3.5 text-slate-300 text-sm truncate max-w-[150px]">{c.sender}</td>
                                            <td className="px-4 py-3.5"><CategoryBadge category={c.classification_category} /></td>
                                            <td className="px-4 py-3.5 min-w-[100px]"><ConfidenceMeter score={c.confidence_score} /></td>
                                            <td className="px-4 py-3.5"><StatusBadge status={c.status} /></td>
                                            <td className="px-4 py-3.5 text-slate-300 text-sm text-center">{c.email_count}</td>
                                            <td className="px-4 py-3.5 text-slate-400 text-xs whitespace-nowrap">
                                                {format(new Date(c.created_at), 'dd MMM yyyy HH:mm')}
                                            </td>
                                            <td className="px-4 py-3.5 text-slate-400 text-xs whitespace-nowrap">
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
                        <div className="px-4 py-3 border-t border-slate-800 flex items-center justify-between">
                            <span className="text-slate-400 text-sm">
                                Page {page} of {totalPages}
                            </span>
                            <div className="flex gap-2">
                                <button
                                    disabled={page === 1}
                                    onClick={() => setPage(p => p - 1)}
                                    className="px-3 py-1.5 bg-slate-800 text-slate-300 text-sm rounded-lg
                             disabled:opacity-50 hover:bg-slate-700 transition-colors"
                                >
                                    Previous
                                </button>
                                <button
                                    disabled={page === totalPages}
                                    onClick={() => setPage(p => p + 1)}
                                    className="px-3 py-1.5 bg-slate-800 text-slate-300 text-sm rounded-lg
                             disabled:opacity-50 hover:bg-slate-700 transition-colors"
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
