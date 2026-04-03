import { useEffect, useState, useRef } from 'react';
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
    entity_operations:   '3. Entity & Operations Profile',
    employment_profile:  '4. Employment Profile',
    loss_history:        '5. Loss History & Prior Claims',
    internet_research:   '6. Internet Research Summary',
    uw_opinion:          '7. UW Opinion & Recommendation',
};

type SectionStatus = 'pending' | 'loading' | 'complete' | 'error';

/** Render markdown-ish content (bold, bullets, italic) into JSX */
function MarkdownContent({ text }: { text: string }) {
    const lines = text.split('\n');
    return (
        <div className="space-y-1">
            {lines.map((line, i) => {
                const trimmed = line.trim();
                if (!trimmed) return <div key={i} className="h-2" />;

                // Bold-only header: **text**
                if (trimmed.startsWith('**') && trimmed.endsWith('**') && !trimmed.slice(2, -2).includes('**')) {
                    return <p key={i} className="font-bold text-slate-800 mt-3 mb-1">{trimmed.slice(2, -2)}</p>;
                }
                // Bullet
                if (trimmed.startsWith('- ')) {
                    return (
                        <p key={i} className="flex gap-2 text-sm text-slate-700">
                            <span className="text-indigo-400 mt-0.5">•</span>
                            <span>{renderInline(trimmed.slice(2))}</span>
                        </p>
                    );
                }
                // Italic
                if (trimmed.startsWith('_') && trimmed.endsWith('_')) {
                    return <p key={i} className="text-sm text-slate-500 italic">{trimmed.slice(1, -1)}</p>;
                }
                return <p key={i} className="text-sm text-slate-700">{renderInline(trimmed)}</p>;
            })}
        </div>
    );
}

function renderInline(text: string): React.ReactNode {
    // Handle **bold:** value patterns
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    return parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
            return <strong key={i} className="font-semibold text-slate-800">{part.slice(2, -2)}</strong>;
        }
        return part;
    });
}

export function UWWorksheetModal({ caseId, onClose }: Props) {
    const [sections, setSections] = useState<Map<string, UWSection>>(new Map());
    const [statuses, setStatuses] = useState<Map<string, SectionStatus>>(
        new Map(SECTION_KEYS.map(k => [k, 'pending']))
    );
    const [generating, setGenerating] = useState(false);
    const [done, setDone] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [downloading, setDownloading] = useState(false);
    const [editingKey, setEditingKey] = useState<string | null>(null);
    const [editValue, setEditValue] = useState('');
    const [collapsedSections, setCollapsedSections] = useState<Set<string>>(new Set());
    const abortRef = useRef<AbortController | null>(null);
    const bottomRef = useRef<HTMLDivElement>(null);

    // On mount: try to load existing worksheet first, then auto-generate
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
                for (const s of data.sections || []) {
                    map.set(s.section_key, s);
                    statusMap.set(s.section_key, 'complete');
                }
                setSections(map);
                setStatuses(statusMap);
                setDone(true);
                return;
            }
        } catch {
            // not found — generate
        }
        generate();
    };

    const generate = async () => {
        // Reset state
        setSections(new Map());
        setStatuses(new Map(SECTION_KEYS.map(k => [k, 'pending'])));
        setDone(false);
        setError(null);
        setGenerating(true);

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
                buf = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const event = JSON.parse(line.slice(6));
                        handleEvent(event);
                    } catch {
                        // ignore parse errors
                    }
                }
            }
        } catch (e: any) {
            if (e?.name !== 'AbortError') {
                setError(e?.message || 'Generation failed');
            }
        } finally {
            setGenerating(false);
        }
    };

    const handleEvent = (event: any) => {
        if (event.type === 'section_start') {
            setStatuses(prev => new Map(prev).set(event.section, 'loading'));
        } else if (event.type === 'section_complete') {
            const section: UWSection = {
                section_key: event.section,
                title: SECTION_TITLES[event.section] || event.section,
                content: event.content,
            };
            setSections(prev => new Map(prev).set(event.section, section));
            setStatuses(prev => new Map(prev).set(event.section, 'complete'));
            // Auto-scroll to bottom
            setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
        } else if (event.type === 'done') {
            setDone(true);
        } else if (event.type === 'error') {
            setError(event.message);
        }
    };

    const handleSave = async () => {
        setSaving(true);
        setSaved(false);
        try {
            const sectionList = Array.from(sections.values());
            await fetch(`/api/cases/${caseId}/uw-worksheet`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sections: sectionList }),
            });
            setSaved(true);
            setTimeout(() => setSaved(false), 3000);
        } catch (e: any) {
            setError('Save failed: ' + e.message);
        } finally {
            setSaving(false);
        }
    };

    const handleDownload = async () => {
        setDownloading(true);
        try {
            const resp = await fetch(`/api/cases/${caseId}/uw-worksheet/download`);
            if (!resp.ok) throw new Error('Download failed');
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `UW_Worksheet_${caseId.slice(0, 8)}.docx`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setDownloading(false);
        }
    };

    const startEdit = (key: string) => {
        const section = sections.get(key);
        if (!section) return;
        setEditValue(section.content);
        setEditingKey(key);
    };

    const saveEdit = () => {
        if (!editingKey) return;
        const existing = sections.get(editingKey);
        if (!existing) return;
        setSections(prev => new Map(prev).set(editingKey, { ...existing, content: editValue }));
        setEditingKey(null);
        setSaved(false);
    };

    const toggleCollapse = (key: string) => {
        setCollapsedSections(prev => {
            const next = new Set(prev);
            if (next.has(key)) next.delete(key);
            else next.add(key);
            return next;
        });
    };

    const completedCount = Array.from(statuses.values()).filter(s => s === 'complete').length;
    const totalSections = SECTION_KEYS.length;

    return (
        <div
            style={{
                position: 'fixed', inset: 0, zIndex: 9999,
                background: 'rgba(0,0,0,0.55)', backdropFilter: 'blur(4px)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '24px',
            }}
            onClick={e => { if (e.target === e.currentTarget) onClose(); }}
        >
            <div style={{
                background: '#fff', borderRadius: '20px', width: '100%', maxWidth: '860px',
                height: '90vh', display: 'flex', flexDirection: 'column',
                boxShadow: '0 40px 80px rgba(0,0,0,0.25)',
                overflow: 'hidden',
            }}>
                {/* Header */}
                <div style={{
                    padding: '16px 24px', borderBottom: '1px solid #e2e8f0',
                    background: 'linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%)',
                    display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0,
                }}>
                    <div style={{
                        width: 36, height: 36, borderRadius: 10,
                        background: 'rgba(99,102,241,0.3)', border: '1px solid rgba(99,102,241,0.5)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                        <FileText size={18} color="#818cf8" />
                    </div>
                    <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 16, fontWeight: 800, color: '#fff' }}>UW Worksheet</div>
                        <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', marginTop: 2 }}>
                            {generating
                                ? `Generating... ${completedCount}/${totalSections} sections complete`
                                : done
                                    ? `${totalSections} sections · Management Liability`
                                    : 'Loading...'}
                        </div>
                    </div>
                    {/* Progress bar */}
                    {generating && (
                        <div style={{ width: 120, height: 4, background: 'rgba(255,255,255,0.1)', borderRadius: 2, overflow: 'hidden' }}>
                            <div style={{
                                height: '100%', background: '#818cf8', borderRadius: 2,
                                width: `${(completedCount / totalSections) * 100}%`,
                                transition: 'width 0.4s ease',
                            }} />
                        </div>
                    )}
                    {done && (
                        <div style={{ display: 'flex', gap: 8 }}>
                            <button
                                onClick={generate}
                                title="Regenerate"
                                style={{
                                    padding: '6px 10px', background: 'rgba(255,255,255,0.08)',
                                    border: '1px solid rgba(255,255,255,0.15)', borderRadius: 8,
                                    color: 'rgba(255,255,255,0.7)', cursor: 'pointer',
                                    display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600,
                                }}
                            >
                                <RefreshCw size={13} /> Regenerate
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={saving}
                                style={{
                                    padding: '6px 12px', background: saved ? '#22c55e' : 'rgba(255,255,255,0.1)',
                                    border: '1px solid rgba(255,255,255,0.2)', borderRadius: 8,
                                    color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', gap: 5, transition: 'background 0.2s',
                                }}
                            >
                                {saving ? <Loader2 size={13} className="animate-spin" /> : saved ? <CheckCircle2 size={13} /> : <Save size={13} />}
                                {saved ? 'Saved!' : 'Save'}
                            </button>
                            <button
                                onClick={handleDownload}
                                disabled={downloading}
                                style={{
                                    padding: '6px 12px', background: '#4f46e5',
                                    border: '1px solid #4338ca', borderRadius: 8,
                                    color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 700,
                                    display: 'flex', alignItems: 'center', gap: 5,
                                }}
                            >
                                {downloading ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                                Word
                            </button>
                        </div>
                    )}
                    <button
                        onClick={onClose}
                        style={{ padding: 6, background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(255,255,255,0.5)', display: 'flex' }}
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Error banner */}
                {error && (
                    <div style={{
                        padding: '10px 24px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
                        display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: '#dc2626', flexShrink: 0,
                    }}>
                        <AlertCircle size={15} />
                        {error}
                    </div>
                )}

                {/* Sections scroll area */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {SECTION_KEYS.map(key => {
                        const status = statuses.get(key) || 'pending';
                        const section = sections.get(key);
                        const isCollapsed = collapsedSections.has(key);

                        return (
                            <div key={key} style={{
                                borderRadius: 14, border: '1px solid',
                                borderColor: status === 'complete' ? '#e2e8f0' : status === 'loading' ? '#c7d2fe' : '#f1f5f9',
                                background: status === 'complete' ? '#fff' : status === 'loading' ? '#f8f7ff' : '#f8fafc',
                                overflow: 'hidden', transition: 'all 0.3s',
                            }}>
                                {/* Section header */}
                                <div
                                    style={{
                                        padding: '10px 16px',
                                        display: 'flex', alignItems: 'center', gap: 10,
                                        background: status === 'loading' ? 'rgba(99,102,241,0.04)' : 'transparent',
                                        cursor: status === 'complete' ? 'pointer' : 'default',
                                        userSelect: 'none',
                                    }}
                                    onClick={() => status === 'complete' && toggleCollapse(key)}
                                >
                                    {status === 'loading' && <Loader2 size={14} className="animate-spin" style={{ color: '#6366f1', flexShrink: 0 }} />}
                                    {status === 'complete' && <CheckCircle2 size={14} style={{ color: '#22c55e', flexShrink: 0 }} />}
                                    {status === 'pending' && (
                                        <div style={{ width: 14, height: 14, borderRadius: '50%', border: '1.5px solid #cbd5e1', flexShrink: 0 }} />
                                    )}

                                    <span style={{
                                        fontSize: 13, fontWeight: 700,
                                        color: status === 'complete' ? '#1e293b' : status === 'loading' ? '#4f46e5' : '#94a3b8',
                                        flex: 1,
                                    }}>
                                        {SECTION_TITLES[key]}
                                    </span>

                                    {status === 'loading' && (
                                        <span style={{ fontSize: 10, color: '#6366f1', fontWeight: 700, background: '#ede9fe', padding: '2px 8px', borderRadius: 99 }}>
                                            Generating...
                                        </span>
                                    )}

                                    {status === 'complete' && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                            {editingKey !== key && (
                                                <button
                                                    onClick={e => { e.stopPropagation(); startEdit(key); }}
                                                    style={{
                                                        padding: '3px 8px', background: 'none',
                                                        border: '1px solid #e2e8f0', borderRadius: 6,
                                                        cursor: 'pointer', color: '#94a3b8',
                                                        display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, fontWeight: 600,
                                                    }}
                                                >
                                                    <Edit3 size={11} /> Edit
                                                </button>
                                            )}
                                            {isCollapsed ? <ChevronDown size={14} style={{ color: '#94a3b8' }} /> : <ChevronUp size={14} style={{ color: '#94a3b8' }} />}
                                        </div>
                                    )}
                                </div>

                                {/* Content */}
                                {status === 'complete' && section && !isCollapsed && (
                                    <div style={{ padding: '0 16px 16px', borderTop: '1px solid #f1f5f9' }}>
                                        {editingKey === key ? (
                                            <div style={{ marginTop: 12 }}>
                                                <textarea
                                                    value={editValue}
                                                    onChange={e => setEditValue(e.target.value)}
                                                    style={{
                                                        width: '100%', minHeight: 180,
                                                        padding: '10px 12px', borderRadius: 8,
                                                        border: '1.5px solid #c7d2fe', fontSize: 13,
                                                        fontFamily: 'inherit', lineHeight: 1.6, resize: 'vertical',
                                                        outline: 'none', boxSizing: 'border-box',
                                                    }}
                                                />
                                                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                                                    <button
                                                        onClick={saveEdit}
                                                        style={{
                                                            padding: '6px 14px', background: '#4f46e5', color: '#fff',
                                                            border: 'none', borderRadius: 7, cursor: 'pointer',
                                                            fontSize: 12, fontWeight: 700,
                                                        }}
                                                    >
                                                        Apply
                                                    </button>
                                                    <button
                                                        onClick={() => setEditingKey(null)}
                                                        style={{
                                                            padding: '6px 14px', background: '#f1f5f9', color: '#64748b',
                                                            border: 'none', borderRadius: 7, cursor: 'pointer',
                                                            fontSize: 12, fontWeight: 600,
                                                        }}
                                                    >
                                                        Cancel
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <div style={{ marginTop: 10 }}>
                                                <MarkdownContent text={section.content} />
                                            </div>
                                        )}
                                    </div>
                                )}
                            </div>
                        );
                    })}

                    <div ref={bottomRef} />
                </div>

                {/* Footer */}
                {done && (
                    <div style={{
                        padding: '12px 24px', borderTop: '1px solid #e2e8f0',
                        background: '#f8fafc', display: 'flex', justifyContent: 'flex-end', gap: 10, flexShrink: 0,
                    }}>
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-white border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors"
                        >
                            {saving ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
                            {saved ? 'Saved!' : 'Save Changes'}
                        </button>
                        <button
                            onClick={handleDownload}
                            disabled={downloading}
                            className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors"
                        >
                            {downloading ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
                            Download Word
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
