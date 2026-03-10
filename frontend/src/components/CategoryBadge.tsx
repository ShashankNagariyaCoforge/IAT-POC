
import type { ClassificationCategory } from '../types';

const CATEGORY_CONFIG: Record<ClassificationCategory, { className: string }> = {
    'New': { className: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
    'Renewal': { className: 'bg-cyan-50 text-cyan-700 border border-cyan-200' },
    'Query/General': { className: 'bg-blue-50 text-[#00467F] border border-blue-200' },
    'Follow-up': { className: 'bg-purple-50 text-purple-700 border border-purple-200' },
    'Complaint/Escalation': { className: 'bg-red-50 text-red-700 border border-red-200' },
    'Regulatory/Legal': { className: 'bg-amber-50 text-amber-700 border border-amber-200' },
    'Documentation/Evidence': { className: 'bg-teal-50 text-teal-700 border border-teal-200' },
    'Spam/Irrelevant': { className: 'bg-gray-100 text-gray-500 border border-gray-200' },
    'BOR': { className: 'bg-orange-50 text-orange-700 border border-orange-200' },
};

interface CategoryBadgeProps {
    category: ClassificationCategory | null;
}

export function CategoryBadge({ category }: CategoryBadgeProps) {
    if (!category) return <span className="text-gray-400 text-xs">—</span>;
    const config = CATEGORY_CONFIG[category] ?? { className: 'bg-gray-100 text-gray-600 border border-gray-200' };
    return (
        <span className={`inline-flex items-center rounded-full text-xs px-2.5 py-1 font-medium ${config.className}`}>
            {category}
        </span>
    );
}
