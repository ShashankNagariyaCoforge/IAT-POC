import { ShieldCheck, CheckCircle2, Loader2 } from 'lucide-react';

interface AuditStep {
    label: string;
    confidence: number;
    detail?: string;
    status: 'completed' | 'active' | 'pending' | 'failed' | 'warning';
}

interface Props {
    steps: AuditStep[];
    caseId?: string;
}

function confColor(pct: number): { bg: string; text: string; border: string } {
    if (pct >= 90) return { bg: '#ecfdf5', text: '#15803d', border: '#86efac' };
    if (pct >= 70) return { bg: '#fffbeb', text: '#b45309', border: '#fcd34d' };
    return { bg: '#fff1f2', text: '#be123c', border: '#fda4af' };
}

export function AuditTrailPanel({ steps, caseId }: Props) {
    return (
        <div style={{
            background: '#ffffff', border: '1px solid #e2e8f0',
            borderRadius: '20px', padding: '20px',
            position: 'sticky', top: '88px',
        }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '20px' }}>
                <ShieldCheck size={14} style={{ color: '#4f46e5' }} />
                <h3 style={{ margin: 0, fontSize: '10px', fontWeight: 900, color: '#0f172a', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
                    Audit Trail
                </h3>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {steps.map((step, i) => {
                    const cc = confColor(step.confidence);
                    const isDone = step.status === 'completed';
                    const isFailed = step.status === 'failed';
                    const isActive = step.status === 'active';
                    return (
                        <div
                            key={i}
                            style={{
                                border: `1px solid ${isFailed ? '#fecdd3' : '#f1f5f9'}`,
                                borderRadius: '12px',
                                padding: '12px',
                                background: isFailed ? '#fff1f2' : '#f8fafc',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px', marginBottom: '6px' }}>
                                <span style={{ fontSize: '9px', fontWeight: 900, color: isFailed ? '#be123c' : '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.1em', flex: 1 }}>
                                    {step.label}
                                </span>
                                <span style={{
                                    fontSize: '9px', fontWeight: 800,
                                    padding: '2px 6px', borderRadius: '6px',
                                    background: cc.bg, color: cc.text, border: `1px solid ${cc.border}`,
                                    flexShrink: 0,
                                }}>
                                    {step.confidence}%
                                </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                {isActive
                                    ? <Loader2 size={11} style={{ color: '#4f46e5', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                                    : isDone
                                        ? <CheckCircle2 size={11} style={{ color: '#22c55e', flexShrink: 0 }} />
                                        : isFailed
                                            ? <span style={{ fontSize: '11px', color: '#dc2626' }}>✗</span>
                                            : <span style={{ width: 11, height: 11, borderRadius: '50%', background: '#e2e8f0', display: 'inline-block', flexShrink: 0 }} />
                                }
                                <p style={{ margin: 0, fontSize: '11px', fontWeight: 600, color: isFailed ? '#dc2626' : '#475569' }}>
                                    {step.detail || (isDone ? 'Completed' : isActive ? 'Running…' : 'Pending')}
                                </p>
                            </div>
                        </div>
                    );
                })}
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '16px' }}>
                <ShieldCheck size={11} style={{ color: '#22c55e' }} />
                <span style={{ fontSize: '9px', fontWeight: 900, color: '#22c55e', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    Integrity Verified
                </span>
            </div>
        </div>
    );
}
