import React from 'react';
import type { ClassificationCategory } from '../types';

const CATEGORY_CONFIG: Record<ClassificationCategory, { className: string }> = {
    'New': { className: 'bg-emerald-900/50 text-emerald-300' },
    'Renewal': { className: 'bg-cyan-900/50 text-cyan-300' },
    'Query/General': { className: 'bg-blue-900/50 text-blue-300' },
    'Follow-up': { className: 'bg-purple-900/50 text-purple-300' },
    'Complaint/Escalation': { className: 'bg-red-900/50 text-red-300' },
    'Regulatory/Legal': { className: 'bg-amber-900/50 text-amber-300' },
    'Documentation/Evidence': { className: 'bg-teal-900/50 text-teal-300' },
    'Spam/Irrelevant': { className: 'bg-slate-700 text-slate-400' },
};

interface CategoryBadgeProps {
    category: ClassificationCategory | null;
}

export function CategoryBadge({ category }: CategoryBadgeProps) {
    if (!category) return <span className="text-slate-500 text-xs">—</span>;
    const config = CATEGORY_CONFIG[category] ?? { className: 'bg-slate-700 text-slate-300' };
    return (
        <span className={`inline-flex items-center rounded-full text-xs px-2.5 py-1 font-medium ${config.className}`}>
            {category}
        </span>
    );
}
