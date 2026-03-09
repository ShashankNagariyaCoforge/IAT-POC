import { createContext, useContext, useRef, useCallback } from 'react';

interface PipelineSnapshot {
    orchestrationResult: unknown | null;
    revealIndex: number;
}

interface PipelineContextValue {
    getSnapshot: (caseId: string) => PipelineSnapshot | null;
    setSnapshot: (caseId: string, snapshot: Partial<PipelineSnapshot>) => void;
    clearSnapshot: (caseId: string) => void;
}

const PipelineContext = createContext<PipelineContextValue>({
    getSnapshot: () => null,
    setSnapshot: () => { },
    clearSnapshot: () => { },
});

export function PipelineProvider({ children }: { children: React.ReactNode }) {
    const cache = useRef<Map<string, PipelineSnapshot>>(new Map());

    const getSnapshot = useCallback((caseId: string) => {
        return cache.current.get(caseId) ?? null;
    }, []);

    const setSnapshot = useCallback((caseId: string, snapshot: Partial<PipelineSnapshot>) => {
        const existing = cache.current.get(caseId) ?? { orchestrationResult: null, revealIndex: 0 };
        cache.current.set(caseId, { ...existing, ...snapshot });
    }, []);

    const clearSnapshot = useCallback((caseId: string) => {
        cache.current.delete(caseId);
    }, []);

    return (
        <PipelineContext.Provider value={{ getSnapshot, setSnapshot, clearSnapshot }}>
            {children}
        </PipelineContext.Provider>
    );
}

export function usePipeline() {
    return useContext(PipelineContext);
}
