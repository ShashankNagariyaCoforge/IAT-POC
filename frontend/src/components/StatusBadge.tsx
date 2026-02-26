import React from 'react';
import type { CaseStatus } from '../types';

const STATUS_CONFIG: Record<CaseStatus, { label: string; className: string }> = {
    RECEIVED: { label: 'Received', className: 'bg-slate-700 text-slate-200' },
    PROCESSING: { label: 'Processing', className: 'bg-yellow-900/50 text-yellow-300 animate-pulse' },
    CLASSIFIED: { label: 'Classified', className: 'bg-green-900/50 text-green-300' },
    PENDING_REVIEW: { label: 'Pending Review', className: 'bg-orange-900/50 text-orange-300' },
    NOTIFIED: { label: 'Notified', className: 'bg-blue-900/50 text-blue-300' },
    FAILED: { label: 'Failed', className: 'bg-red-900/50 text-red-300' },
};

interface StatusBadgeProps {
    status: CaseStatus;
    size?: 'sm' | 'md';
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
    const config = STATUS_CONFIG[status] ?? { label: status, className: 'bg-slate-700 text-slate-200' };
    const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-xs px-2.5 py-1';
    return (
        <span className={`inline-flex items-center rounded-full font-medium ${sizeClass} ${config.className}`}>
            {config.label}
        </span>
    );
}
