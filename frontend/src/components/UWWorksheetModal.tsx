import { useEffect, useState, useRef, useCallback } from 'react';
import { X, Download, Save, Loader2, CheckCircle2, AlertCircle, RefreshCw, FileText, ChevronDown, ChevronUp, Edit3 } from 'lucide-react';

interface UWSection {
    section_key: string;
    title: string;
    content: string;
}

interface Props {
    caseId: string;
    onClose: () => void;
}

const SECTION_KEYS = [
    'submission_overview',
    'proposed_program',
    'entity_operations',
    'employment_profile',
    'loss_history',
    'internet_research',
    'uw_opinion',
];

const SECTION_TITLES: Record<string, string> = {
    submission_overview: '1. Submission Overview',
    proposed_program:    '2. Proposed Program Terms',
    entity_operations:  '3. Entity & Operations Profile',
    employment_profile:  '4. Employment Profile',
    loss_history:        '5. Loss History & Prior Claims',
    internet_research:   '6. Internet Research Summary',
    uw_opinion:          '7. UW Opinion & Recommendation',
};

type SectionStatus = 'pending' | 'loading' | 'complete';

// ── Inline markdown renderer ──────────────────────────────────────────────────
function renderInline(text: string): React.ReactNode {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) =>
        part.startsWith('**') && part.endsWith('**')
            ? <strong key={i} style={{ fontWeight: 700, color: '#1e293b' }}>{part.slice(2, -2)}</strong>
            : <span key={i}>{part}</span>
    );
}

function MarkdownContent({ text }: { text: string }) {
    const lines = text.split('\n');
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {lines.map((line, i) => {
                const t = line.trim();
                if (!t) return <div key={i} style={{ height: 8 }} />;

                // Pure bold header: **text** (no inline content after)
                if (/^\*\*[^*]+\*\*$/.test(t)) {
                    return (
                        <p key={i} style={{
                            fontWeight: 700, color: '#0f172a', fontSize: 13,
                            marginTop: 12, marginBottom: 2,
                        }}>
                            {t.slice(2, -2)}
                        </p>
                    );
                }
                // Bullet
                if (t.startsWith('- ')) {
                    return (
                        <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                            <span style={{ color: '#6366f1', fontSize: 14, lineHeight: '20px', flexShrink: 0 }}>•</span>
                            <span style={{ fontSize: 13, color: '#374151', lineHeight: '20px' }}>
                                {renderInline(t.slice(2))}
                            </span>
                        </div>
                    );
                }
                // Italic / placeholder
                if (t.startsWith('_') && t.endsWith('_')) {
                    return <p key={i} style={{ fontSize: 13, color: '#94a3b8', fontStyle: 'italic' }}>{t.slice(1, -1)}</p>;
                }
                // Normal line (may contain inline bold)
                return (
                    <p key={i} style={{ fontSize: 13, color: '#374151', lineHeight: '20px' }}>
                        {renderInline(t)}
                    </p>
                );
            })}
        </div>
    );
}

// ── Auto-sizing textarea ──────────────────────────────────────────────────────
function AutoTextarea({
    value,
    onChange,
}: {
    value: string;
    onChange: (v: string) => void;
}) {
    const ref = useRef<HTMLTextAreaElement>(null);

    // Resize to fit content on every value change
    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = `${el.scrollHeight}px`;
    }, [value]);

    return (
        <textarea
            ref={ref}
            value={value}
            onChange={e => onChange(e.target.value)}
            style={{
                width: '100%',
                minHeight: 120,
                padding: '10px 14px',
                borderRadius: 8,
                border: '1.5px solid #c7d2fe',
                fontSize: 13,
                fontFamily: 'inherit',
                lineHeight: 1.6,
                resize: 'none',           // disable manual resize — we auto-size
                outline: 'none',
                boxSizing: 'border-box',
                display: 'block',
                overflow: 'hidden',       // hides scrollbar while auto-sizing
                color: '#1e293b',
                background: '#fafbff',
            }}
        />
    );
}

// ── Single section card ───────────────────────────────────────────────────────
function SectionCard({
    sectionKey,
    status,
    section,
    isCollapsed,
    isEditing,
    editValue,
    onToggleCollapse,
    onStartEdit,
    onEditChange,
    onApplyEdit,
    onCancelEdit,
}: {
    sectionKey: string;
    status: SectionStatus;
    section: UWSection | undefined;
    isCollapsed: boolean;
    isEditing: boolean;
    editValue: string;
    onToggleCollapse: () => void;
    onStartEdit: () => void;
    onEditChange: (v: string) => void;
    onApplyEdit: () => void;
    onCancelEdit: () => void;
}) {
    const isComplete = status === 'complete';
    const isLoading = status === 'loading';

    return (
        <div style={{
            borderRadius: 12,
            border: `1px solid ${isComplete ? '#e2e8f0' : isLoading ? '#c7d2fe' : '#f1f5f9'}`,
            background: isComplete ? '#ffffff' : isLoading ? '#f8f7ff' : '#f9fafb',
            // NO overflow:hidden — that's what causes clipping. Border-radius works without it on block elements.
        }}>
            {/* Row: icon · title · badges · actions */}
            <div
                onClick={isComplete && !isEditing ? onToggleCollapse : undefined}
                style={{
                    padding: '12px 16px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 10,
                    cursor: isComplete && !isEditing ? 'pointer' : 'default',
                    userSelect: 'none',
                    borderRadius: isCollapsed ? 12 : '12px 12px 0 0',
                }}
            >
                {/* Status icon */}
                {isLoading && <Loader2 size={15} style={{ color: '#6366f1', flexShrink: 0, animation: 'spin 1s linear infinite' }} />}
                {isComplete && <CheckCircle2 size={15} style={{ color: '#22c55e', flexShrink: 0 }} />}
                {status === 'pending' && (
                    <div style={{ width: 15, height: 15, borderRadius: '50%', border: '1.5px solid #cbd5e1', flexShrink: 0 }} />
                )}

                {/* Title */}
                <span style={{
                    fontSize: 13,
                    fontWeight: 700,
                    color: isComplete ? '#0f172a' : isLoading ? '#4f46e5' : '#94a3b8',
                    flex: 1,
                }}>
                    {SECTION_TITLES[sectionKey]}
                </span>

                {isLoading && (
                    <span style={{
                        fontSize: 10, fontWeight: 700, color: '#6366f1',
                        background: '#ede9fe', padding: '2px 8px', borderRadius: 99,
                    }}>
                        Generating…
                    </span>
                )}

                {isComplete && !isEditing && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <button
                            onClick={e => { e.stopPropagation(); onStartEdit(); }}
                            style={{
                                padding: '3px 9px',
                                background: 'transparent',
                                border: '1px solid #e2e8f0',
                                borderRadius: 6,
                                cursor: 'pointer',
                                color: '#64748b',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                fontSize: 11,
                                fontWeight: 600,
                            }}
                        >
                            <Edit3 size={10} /> Edit
                        </button>
                        {isCollapsed
                            ? <ChevronDown size={15} style={{ color: '#94a3b8' }} />
                            : <ChevronUp size={15} style={{ color: '#94a3b8' }} />}
                    </div>
                )}

                {isEditing && (
                    <span style={{ fontSize: 11, color: '#f59e0b', fontWeight: 700 }}>Editing…</span>
                )}
            </div>

            {/* Content area — only rendered when complete and not collapsed */}
            {isComplete && section && !isCollapsed && (
                <div style={{
                    padding: '0 16px 16px',
                    borderTop: '1px solid #f1f5f9',
                }}>
                    {isEditing ? (
                        <div style={{ marginTop: 12 }}>
                            <AutoTextarea value={editValue} onChange={onEditChange} />
                            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                                <button
                                    onClick={onApplyEdit}
                                    style={{
                                        padding: '7px 16px',
                                        background: '#4f46e5',
                                        color: '#fff',
                                        border: 'none',
                                        borderRadius: 7,
                                        cursor: 'pointer',
                                        fontSize: 12,
                                        fontWeight: 700,
                                    }}
                                >
                                    Apply
                                </button>
                                <button
                                    onClick={onCancelEdit}
                                    style={{
                                        padding: '7px 16px',
                                        background: '#f1f5f9',
                                        color: '#64748b',
                                        border: 'none',
                                        borderRadius: 7,
                                        cursor: 'pointer',
                                        fontSize: 12,
                                        fontWeight: 600,
                                    }}
                                >
                                    Cancel
                                </button>
                            </div>
                        </div>
                    ) : (
                        <div style={{ marginTop: 12 }}>
                            <MarkdownContent text={section.content} />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// ── Main modal ────────────────────────────────────────────────────────────────
export function UWWorksheetModal({ caseId, onClose }: Props) {
    const [sections, setSections] = useState<Map<string, UWSection>>(new Map());
    const [statuses, setStatuses] = useState<Map<string, SectionStatus>>(
        new Map(SECTION_KEYS.map(k => [k, 'pending']))
    );
    const [generating, setGenerating] = useState(false);
    const [done, setDone] = useState(false);
    const [globalError, setGlobalError] = useState<string | null>(null);

    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [downloading, setDownloading] = useState(false);

    // One edit at a time
    const [editingKey, setEditingKey] = useState<string | null>(null);
    const [editValue, setEditValue] = useState('');

    // Collapsed state — default all expanded
    const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

    const abortRef = useRef<AbortController | null>(null);
    const scrollRef = useRef<HTMLDivElement>(null);
    // Track whether user has scrolled up manually so we don't force-scroll them back down
    const userScrolledUp = useRef(false);

    // ── Load or generate on open ────────────────────────────────────────────
    useEffect(() => {
        loadOrGenerate();
        return () => abortRef.current?.abort();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const loadOrGenerate = async () => {
        try {
            const resp = await fetch(`/api/cases/${caseId}/uw-worksheet`);
            if (resp.ok) {
                const data = await resp.json();
                const map = new Map<string, UWSection>();
                const statusMap = new Map<string, SectionStatus>(SECTION_KEYS.map(k => [k, 'pending']));
                for (const s of (data.sections || []) as UWSection[]) {
                    map.set(s.section_key, s);
                    statusMap.set(s.section_key, 'complete');
                }
                setSections(map);
                setStatuses(statusMap);
                setDone(true);
                return;
            }
        } catch {
            /* not found — fall through to generate */
        }
        generate();
    };

    const generate = useCallback(async () => {
        setSections(new Map());
        setStatuses(new Map(SECTION_KEYS.map(k => [k, 'pending'])));
        setDone(false);
        setGlobalError(null);
        setGenerating(true);
        setEditingKey(null);
        userScrolledUp.current = false;

        abortRef.current?.abort();
        const ctrl = new AbortController();
        abortRef.current = ctrl;

        try {
            const resp = await fetch(`/api/cases/${caseId}/uw-worksheet/generate`, {
                method: 'POST',
                signal: ctrl.signal,
            });
            if (!resp.ok) throw new Error(`Server error: ${resp.status}`);
            if (!resp.body) throw new Error('No response body');

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done: streamDone, value } = await reader.read();
                if (streamDone) break;
                buf += decoder.decode(value, { stream: true });

                const lines = buf.split('\n');
                buf = lines.pop() ?? '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        handleEvent(event);
                    } catch { /* ignore malformed SSE lines */ }
                }
            }
        } catch (e: any) {
            if (e?.name !== 'AbortError') {
                setGlobalError(e?.message ?? 'Generation failed');
            }
        } finally {
            setGenerating(false);
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [caseId]);

    const handleEvent = (event: any) => {
        if (event.type === 'section_start') {
            setStatuses(prev => new Map(prev).set(event.section, 'loading'));
            // Only auto-scroll if the user hasn't scrolled away
            if (!userScrolledUp.current) {
                requestAnimationFrame(() => {
                    const el = scrollRef.current;
                    if (el) el.scrollTop = el.scrollHeight;
                });
            }
        } else if (event.type === 'section_complete') {
            const section: UWSection = {
                section_key: event.section,
                title: SECTION_TITLES[event.section] ?? event.section,
                content: event.content,
            };
            setSections(prev => new Map(prev).set(event.section, section));
            setStatuses(prev => new Map(prev).set(event.section, 'complete'));
            if (!userScrolledUp.current) {
                requestAnimationFrame(() => {
                    const el = scrollRef.current;
                    if (el) el.scrollTop = el.scrollHeight;
                });
            }
        } else if (event.type === 'done') {
            setDone(true);
        } else if (event.type === 'error') {
            setGlobalError(event.message);
        }
    };

    // Detect manual scroll-up so we stop auto-scrolling
    const handleScroll = () => {
        const el = scrollRef.current;
        if (!el) return;
        const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
        userScrolledUp.current = !nearBottom;
    };

    // ── Save / Download ─────────────────────────────────────────────────────
    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        try {
            const sectionList = Array.from(sections.values());
            const resp = await fetch(`/api/cases/${caseId}/uw-worksheet`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sections: sectionList }),
            });
            if (!resp.ok) throw new Error(`Save failed (${resp.status})`);
            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
        } catch (e: any) {
            setGlobalError(e.message);
        } finally {
            setSaving(false);
        }
    };

    const handleDownload = async () => {
        setDownloading(true);
        try {
            const resp = await fetch(`/api/cases/${caseId}/uw-worksheet/download`);
            if (!resp.ok) throw new Error(`Download failed (${resp.status})`);
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `UW_Worksheet_${caseId.slice(0, 8)}.docx`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        } catch (e: any) {
            setGlobalError(e.message);
        } finally {
            setDownloading(false);
        }
    };

    // ── Edit helpers ────────────────────────────────────────────────────────
    const startEdit = (key: string) => {
        const section = sections.get(key);
        if (!section) return;
        // Expand it if collapsed
        setCollapsed(prev => { const n = new Set(prev); n.delete(key); return n; });
        setEditValue(section.content);
        setEditingKey(key);
    };

    const applyEdit = () => {
        if (!editingKey) return;
        const existing = sections.get(editingKey);
        if (!existing) return;
        setSections(prev => new Map(prev).set(editingKey, { ...existing, content: editValue }));
        setEditingKey(null);
        setSaved(false);
    };

    const cancelEdit = () => setEditingKey(null);

    const toggleCollapse = (key: string) => {
        setCollapsed(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const completedCount = Array.from(statuses.values()).filter(s => s === 'complete').length;

    return (
        <div
            style={{
                position: 'fixed',
                inset: 0,
                zIndex: 9999,
                background: 'rgba(2, 6, 23, 0.6)',
                backdropFilter: 'blur(6px)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '20px',
            }}
            onClick={e => { if (e.target === e.currentTarget) onClose(); }}
        >
            {/*
              Modal card.
              height: 92vh with display:flex + flexDirection:column ensures the card is bounded.
              overflow:hidden clips rounded corners cleanly.
              The scroll area inside uses flex:1 + minHeight:0 to actually scroll.
            */}
            <div style={{
                background: '#f8fafc',
                borderRadius: 20,
                width: '100%',
                maxWidth: 960,
                height: '92vh',
                display: 'flex',
                flexDirection: 'column',
                boxShadow: '0 32px 64px rgba(0,0,0,0.3), 0 0 0 1px rgba(255,255,255,0.06)',
                overflow: 'hidden',   // clips corners; scroll is on the inner div
            }}>

                {/* ── Header ── */}
                <div style={{
                    padding: '14px 20px',
                    background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    flexShrink: 0,
                    borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}>
                    <div style={{
                        width: 34, height: 34, borderRadius: 9,
                        background: 'rgba(99,102,241,0.25)',
                        border: '1px solid rgba(99,102,241,0.45)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                    }}>
                        <FileText size={16} color="#818cf8" />
                    </div>

                    <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 15, fontWeight: 800, color: '#fff', lineHeight: 1.2 }}>
                            UW Worksheet — Secura Insurance
                        </div>
                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>
                            {generating
                                ? `Generating… ${completedCount} of ${SECTION_KEYS.length} sections complete`
                                : done
                                    ? `${SECTION_KEYS.length} sections complete · Case ${caseId.slice(0, 8)}`
                                    : 'Loading…'}
                        </div>
                    </div>

                    {/* Progress bar (only while generating) */}
                    {generating && (
                        <div style={{
                            width: 100, height: 3,
                            background: 'rgba(255,255,255,0.1)',
                            borderRadius: 2,
                            overflow: 'hidden',
                            flexShrink: 0,
                        }}>
                            <div style={{
                                height: '100%',
                                background: 'linear-gradient(90deg, #6366f1, #818cf8)',
                                borderRadius: 2,
                                width: `${(completedCount / SECTION_KEYS.length) * 100}%`,
                                transition: 'width 0.5s ease',
                            }} />
                        </div>
                    )}

                    {/* Regenerate (only when done) */}
                    {done && (
                        <button
                            onClick={generate}
                            title="Regenerate"
                            style={{
                                padding: '6px 11px',
                                background: 'rgba(255,255,255,0.07)',
                                border: '1px solid rgba(255,255,255,0.12)',
                                borderRadius: 8,
                                color: 'rgba(255,255,255,0.65)',
                                cursor: 'pointer',
                                display: 'flex', alignItems: 'center', gap: 5,
                                fontSize: 12, fontWeight: 600,
                                flexShrink: 0,
                            }}
                        >
                            <RefreshCw size={12} /> Regenerate
                        </button>
                    )}

                    {/* Close */}
                    <button
                        onClick={onClose}
                        style={{
                            padding: 6, background: 'none', border: 'none',
                            cursor: 'pointer', color: 'rgba(255,255,255,0.45)',
                            display: 'flex', flexShrink: 0,
                        }}
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* ── Error banner ── */}
                {globalError && (
                    <div style={{
                        padding: '10px 20px',
                        background: '#fef2f2',
                        borderBottom: '1px solid #fecaca',
                        display: 'flex', alignItems: 'center', gap: 8,
                        fontSize: 13, color: '#dc2626',
                        flexShrink: 0,
                    }}>
                        <AlertCircle size={14} />
                        <span style={{ flex: 1 }}>{globalError}</span>
                        <button
                            onClick={() => setGlobalError(null)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#dc2626' }}
                        >
                            <X size={14} />
                        </button>
                    </div>
                )}

                {/*
                  ── Scroll area ──
                  minHeight: 0 is CRITICAL — without it, flex children won't shrink
                  below their content size, making overflow:auto useless.
                */}
                <div
                    ref={scrollRef}
                    onScroll={handleScroll}
                    style={{
                        flex: 1,
                        minHeight: 0,          // ← the key fix for scroll
                        overflowY: 'auto',
                        padding: '20px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: 10,
                    }}
                >
                    {SECTION_KEYS.map(key => (
                        <SectionCard
                            key={key}
                            sectionKey={key}
                            status={statuses.get(key) ?? 'pending'}
                            section={sections.get(key)}
                            isCollapsed={collapsed.has(key)}
                            isEditing={editingKey === key}
                            editValue={editValue}
                            onToggleCollapse={() => toggleCollapse(key)}
                            onStartEdit={() => startEdit(key)}
                            onEditChange={setEditValue}
                            onApplyEdit={applyEdit}
                            onCancelEdit={cancelEdit}
                        />
                    ))}

                    {/* Spacer so last section doesn't sit right above the footer */}
                    <div style={{ height: 8 }} />
                </div>

                {/* ── Footer (only when done or generating) ── */}
                <div style={{
                    padding: '12px 20px',
                    borderTop: '1px solid #e2e8f0',
                    background: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    gap: 10,
                    flexShrink: 0,
                }}>
                    {done && (
                        <>
                            <button
                                onClick={handleSave}
                                disabled={saving}
                                style={{
                                    padding: '8px 18px',
                                    background: saved ? '#f0fdf4' : '#fff',
                                    border: `1px solid ${saved ? '#86efac' : '#e2e8f0'}`,
                                    borderRadius: 10,
                                    cursor: saving ? 'not-allowed' : 'pointer',
                                    color: saved ? '#16a34a' : '#475569',
                                    fontSize: 13, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    transition: 'all 0.2s',
                                }}
                            >
                                {saving
                                    ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                                    : <Save size={14} />}
                                {saved ? 'Saved!' : 'Save Changes'}
                            </button>

                            <button
                                onClick={handleDownload}
                                disabled={downloading}
                                style={{
                                    padding: '8px 18px',
                                    background: '#4f46e5',
                                    border: '1px solid #4338ca',
                                    borderRadius: 10,
                                    cursor: downloading ? 'not-allowed' : 'pointer',
                                    color: '#fff',
                                    fontSize: 13, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', gap: 6,
                                    boxShadow: '0 2px 8px rgba(79,70,229,0.3)',
                                }}
                            >
                                {downloading
                                    ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                                    : <Download size={14} />}
                                Download Word
                            </button>
                        </>
                    )}

                    {generating && (
                        <span style={{ fontSize: 12, color: '#94a3b8', fontWeight: 600 }}>
                            Generating — {completedCount}/{SECTION_KEYS.length} sections complete…
                        </span>
                    )}

                    <button
                        onClick={onClose}
                        style={{
                            padding: '8px 16px',
                            background: '#f1f5f9',
                            border: '1px solid #e2e8f0',
                            borderRadius: 10,
                            cursor: 'pointer',
                            color: '#64748b',
                            fontSize: 13, fontWeight: 600,
                        }}
                    >
                        Close
                    </button>
                </div>
            </div>
        </div>
    );
}
