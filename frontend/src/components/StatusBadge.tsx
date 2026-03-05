
import type { CaseStatus } from '../types';

const STATUS_CONFIG: Record<CaseStatus, { label: string; className: string }> = {
    RECEIVED: { label: 'Received', className: 'bg-blue-50 text-[#00467F] border border-blue-200' },
    PROCESSING: { label: 'Processing', className: 'bg-amber-50 text-amber-700 border border-amber-200 animate-pulse' },
    CLASSIFIED: { label: 'Classified', className: 'bg-green-50 text-green-700 border border-green-200' },
    PENDING_REVIEW: { label: 'Pending Review', className: 'bg-orange-50 text-orange-700 border border-orange-200' },
    NOTIFIED: { label: 'Notified', className: 'bg-teal-50 text-teal-700 border border-teal-200' },
    FAILED: { label: 'Failed', className: 'bg-red-50 text-red-700 border border-red-200' },
    BLOCKED_SAFETY: { label: 'Blocked', className: 'bg-red-100 text-red-800 border border-red-300 font-bold' },
    NEEDS_REVIEW_SAFETY: { label: 'Needs Review', className: 'bg-yellow-50 text-yellow-700 border border-yellow-300' },
};

interface StatusBadgeProps {
    status: CaseStatus;
    size?: 'sm' | 'md';
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
    const config = STATUS_CONFIG[status] ?? { label: status, className: 'bg-gray-100 text-gray-600 border border-gray-200' };
    const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';
    return (
        <span className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${config.className}`}>
            {config.label}
        </span>
    );
}
