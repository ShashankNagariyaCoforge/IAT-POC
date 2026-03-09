import type { LucideIcon } from 'lucide-react';

interface StatCardProps {
    title: string;
    value: string | number;
    icon: LucideIcon;
    trend?: string;
    trendPositive?: boolean;
    accent?: string; // tailwind color key e.g. 'indigo' | 'emerald' | 'amber' | 'rose'
}

export function StatCard({ title, value, icon: Icon, trend, trendPositive, accent = 'indigo' }: StatCardProps) {
    const colorMap: Record<string, { bg: string; icon: string; trend: string }> = {
        indigo: { bg: '#eef2ff', icon: '#4f46e5', trend: '#4f46e5' },
        emerald: { bg: '#ecfdf5', icon: '#059669', trend: '#059669' },
        amber: { bg: '#fffbeb', icon: '#d97706', trend: '#d97706' },
        rose: { bg: '#fff1f2', icon: '#e11d48', trend: '#e11d48' },
    };
    const colors = colorMap[accent] ?? colorMap.indigo;

    return (
        <div style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '16px',
            padding: '24px',
            boxShadow: '0 1px 6px rgba(0,0,0,0.04)',
            transition: 'box-shadow 0.2s',
            cursor: 'default',
        }}
            onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.08)')}
            onMouseLeave={e => (e.currentTarget.style.boxShadow = '0 1px 6px rgba(0,0,0,0.04)')}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                <div style={{
                    width: '44px', height: '44px', borderRadius: '12px',
                    background: colors.bg, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                    <Icon size={22} color={colors.icon} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{
                        color: '#94a3b8', fontSize: '10px', fontWeight: 700,
                        textTransform: 'uppercase', letterSpacing: '0.1em', margin: '0 0 4px 0',
                    }}>{title}</p>
                    <p style={{ color: '#0f172a', fontSize: '24px', fontWeight: 800, margin: 0, lineHeight: 1, letterSpacing: '-0.02em' }}>
                        {value ?? '—'}
                    </p>
                    {trend && (
                        <p style={{ color: trendPositive ? '#059669' : '#94a3b8', fontSize: '11px', fontWeight: 600, margin: '4px 0 0 0' }}>
                            {trend}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
