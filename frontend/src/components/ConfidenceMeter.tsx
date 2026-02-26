import React from 'react';

interface ConfidenceMeterProps {
    score: number | null;
    showLabel?: boolean;
}

export function ConfidenceMeter({ score, showLabel = true }: ConfidenceMeterProps) {
    if (score === null || score === undefined) return <span className="text-slate-500 text-xs">—</span>;

    const pct = Math.round(score * 100);
    const color =
        pct >= 90 ? 'bg-emerald-500' :
            pct >= 75 ? 'bg-blue-500' :
                pct >= 50 ? 'bg-amber-500' :
                    'bg-red-500';

    return (
        <div className="flex items-center gap-2">
            <div className="flex-1 bg-slate-700 rounded-full h-1.5 min-w-[60px]">
                <div
                    className={`${color} h-1.5 rounded-full transition-all duration-300`}
                    style={{ width: `${pct}%` }}
                />
            </div>
            {showLabel && (
                <span className="text-xs font-medium text-slate-300 min-w-[32px] text-right">{pct}%</span>
            )}
        </div>
    );
}
