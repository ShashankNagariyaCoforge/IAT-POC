interface Props {
    emailCount: number;
    docCount: number;
    progressPct: number;
    message: string;
}

export function IngestionStatsCard({ emailCount, docCount, progressPct, message }: Props) {
    return (
        <div className="bg-indigo-900 rounded-2xl p-6 text-white shadow-lg border border-indigo-800 overflow-hidden relative">
            {/* Background decoration */}
            <div
                className="absolute -top-20 -right-20 w-48 h-48 bg-indigo-500 rounded-full blur-3xl opacity-20 pointer-events-none"
            />

            <div className="flex items-end gap-3 mb-6 relative z-10">
                <h2 className="text-4xl font-black tracking-tighter leading-none m-0 shadow-sm text-white">
                    {docCount}
                </h2>
                <span className="text-indigo-300 font-bold uppercase tracking-wider text-xs pb-1">
                    Files · {progressPct === 100 ? 'Processed' : 'Processing'}
                </span>
            </div>

            <p className="text-[10px] font-bold text-indigo-200 uppercase tracking-widest mb-6 relative z-10">
                Across {emailCount} email{emailCount !== 1 ? 's' : ''}
            </p>

            <div className="space-y-4 relative z-10">
                {/* Progress bar container */}
                <div className="h-2 w-full bg-indigo-950/50 rounded-full overflow-hidden border border-indigo-800/50 shadow-inner">
                    <div
                        className="h-full bg-teal-400 rounded-full transition-all duration-1000 ease-in-out relative"
                        style={{ width: `${progressPct}%` }}
                    >
                        {/* Shimmer effect inside the bar when actively processing */}
                        {progressPct < 100 && (
                            <div
                                className="absolute top-0 left-0 bottom-0 w-20 bg-gradient-to-r from-transparent via-white to-transparent opacity-30 blur-sm"
                                style={{
                                    animation: 'shimmer 1.5s infinite linear',
                                    transform: 'skewX(-20deg)',
                                }}
                            />
                        )}
                    </div>
                </div>

                <p className="text-xs text-indigo-300 font-medium">
                    {message}
                </p>
            </div>

            {/* Global shimmer animation if not defined in index.css */}
            <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-150%) skewX(-20deg); }
          100% { transform: translateX(300%) skewX(-20deg); }
        }
      `}</style>
        </div>
    );
}
