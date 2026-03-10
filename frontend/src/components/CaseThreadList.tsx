import { useEffect, useRef } from 'react';
import { Mail, MailOpen, Paperclip } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Case } from '../types';

export function formatRelativeTime(dateString: string): string {
    try {
        return formatDistanceToNow(new Date(dateString), { addSuffix: true });
    } catch {
        return dateString;
    }
}

interface Props {
    cases: Case[];
    selectedId: string | null;
    onSelect: (id: string) => void;
    isLoading?: boolean;
}

export function CaseThreadList({ cases, selectedId, onSelect, isLoading }: Props) {
    const scrollRef = useRef<HTMLDivElement>(null);

    // Restore scroll position
    useEffect(() => {
        const savedScroll = localStorage.getItem('caseListScroll');
        if (savedScroll && scrollRef.current) {
            scrollRef.current.scrollTop = parseInt(savedScroll, 10);
        }
    }, []);

    // Save scroll position on unmount
    useEffect(() => {
        const el = scrollRef.current;
        return () => {
            if (el) localStorage.setItem('caseListScroll', el.scrollTop.toString());
        };
    }, []);

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'RECEIVED': return 'bg-amber-100 text-amber-700 border-amber-200';
            case 'PROCESSING': return 'bg-indigo-100 text-indigo-700 border-indigo-200';
            case 'PROCESSED':
            case 'CLASSIFIED': return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            case 'BLOCKED_SAFETY':
            case 'NEEDS_REVIEW_SAFETY':
            case 'PENDING_REVIEW': return 'bg-red-100 text-red-700 border-red-200';
            default: return 'bg-slate-100 text-slate-700 border-slate-200';
        }
    };

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 gap-3">
                <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                <p className="text-sm font-semibold">Loading inbox...</p>
            </div>
        );
    }

    return (
        <div
            ref={scrollRef}
            className="flex-1 overflow-y-auto custom-scrollbar bg-slate-50"
            onScroll={(e) => localStorage.setItem('caseListScroll', e.currentTarget.scrollTop.toString())}
        >
            {cases.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-10 text-center text-slate-400">
                    <Mail size={32} className="mb-3 opacity-20" />
                    <p className="text-sm font-semibold text-slate-500">Inbox empty</p>
                </div>
            ) : (
                <div className="flex flex-col">
                    {cases.map((c) => {
                        const isSelected = selectedId === c.case_id;
                        const isNew = c.status === 'RECEIVED';

                        return (
                            <div
                                key={c.case_id}
                                onClick={() => onSelect(c.case_id)}
                                className={`flex gap-3 p-4 border-b border-slate-100 cursor-pointer transition-colors ${isSelected
                                    ? 'bg-indigo-100/50 border-l-4 border-l-indigo-600 pl-3'
                                    : 'bg-white hover:bg-slate-50 border-l-4 border-l-transparent pl-3'
                                    }`}
                            >
                                {/* Icon */}
                                <div className="pt-1 flex-shrink-0">
                                    {isNew ? (
                                        <Mail size={16} className="text-indigo-600" fill="currentColor" opacity={0.2} />
                                    ) : (
                                        <MailOpen size={16} className="text-slate-400" />
                                    )}
                                </div>

                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                    <div className="flex items-center justify-between gap-2 mb-1">
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase tracking-wider ${getStatusColor(c.status)}`}>
                                            {c.status.replace(/_/g, ' ')}
                                        </span>
                                        <span className="text-[10px] text-slate-400 font-semibold whitespace-nowrap">
                                            {formatRelativeTime(c.created_at)}
                                        </span>
                                    </div>

                                    <p className={`text-sm truncate mb-0.5 ${isSelected ? 'text-indigo-900 font-bold' : isNew ? 'text-slate-900 font-bold' : 'text-slate-700 font-semibold'}`}>
                                        {c.sender}
                                    </p>
                                    <p className={`text-[11px] truncate mb-1 ${isSelected ? 'text-indigo-800 font-medium' : isNew ? 'text-slate-800 font-medium' : 'text-slate-500'}`}>
                                        {c.subject}
                                    </p>
                                    <p className="text-[11px] text-slate-400 italic line-clamp-1">
                                        [Case ID: {c.case_id}] Automatically ingested via email pipeline
                                    </p>

                                    {/* Optional Attachment indicator if we had real counts. Just showing 1 as placeholder if not specified. */}
                                    <div className="flex items-center gap-1 mt-2 text-slate-400">
                                        <Paperclip size={10} />
                                        <span className="text-[10px] font-semibold">Attachments included</span>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}
