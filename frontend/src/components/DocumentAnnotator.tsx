import React from 'react';
import { Maximize2, X, AlertCircle } from 'lucide-react';
import { ExtractionInstance } from '../types';

interface DocumentAnnotatorProps {
    caseId: string;
    instances: ExtractionInstance[];
    onClose: () => void;
    onFullscreen: () => void;
}

export const DocumentAnnotator: React.FC<DocumentAnnotatorProps> = ({
    caseId,
    instances,
    onClose,
    onFullscreen
}) => {
    if (instances.length === 0) return null;

    // We assume all instances for a single highlighted row are on the same document/page
    const { doc_id, page, page_width, page_height } = instances[0];

    // Determine color based on confidence
    const getColor = (conf: number) => {
        if (conf > 0.85) return '#10b981'; // emerald-500
        if (conf > 0.50) return '#f59e0b'; // amber-500
        return '#ef4444'; // red-500
    };

    const imageUrl = `/api/cases/${caseId}/documents/${doc_id}/pages/${page}/image`;

    // Calculate overall confidence (min for safer reporting)
    const minConfidence = Math.min(...instances.map(i => i.confidence));
    const footerColor = getColor(minConfidence);

    // Convert polygon to SVG points string with outward padding
    const formatPoints = (poly: number[]) => {
        if (poly.length < 2) return '';

        // Calculate the geometric center to expand outwards
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (let i = 0; i < poly.length; i += 2) {
            minX = Math.min(minX, poly[i]);
            minY = Math.min(minY, poly[i + 1]);
            maxX = Math.max(maxX, poly[i]);
            maxY = Math.max(maxY, poly[i + 1]);
        }

        const cx = (minX + maxX) / 2;
        const cy = (minY + maxY) / 2;

        // Push vertices away from center by a fixed small delta (3 units)
        const points = [];
        for (let i = 0; i < poly.length; i += 2) {
            const dx = poly[i] - cx;
            const dy = poly[i + 1] - cy;
            const mag = Math.sqrt(dx * dx + dy * dy) || 1;
            const px = poly[i] + (dx / mag) * 4; // 4 units of padding
            const py = poly[i + 1] + (dy / mag) * 4;
            points.push(`${px},${py}`);
        }
        return points.join(' ');
    };

    return (
        <div className="flex flex-col h-full bg-slate-900 rounded-2xl overflow-hidden border border-slate-800 shadow-2xl">
            {/* Header */}
            <div className="px-4 py-3 bg-slate-800 border-b border-slate-700 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <div className="flex flex-col">
                        <span className="text-[10px] font-black text-slate-400 uppercase tracking-tighter">Annotated View</span>
                        <span className="text-xs font-bold text-white leading-none">Page {page} of Extraction</span>
                    </div>
                </div>
                <div className="flex items-center gap-1">
                    <button
                        onClick={onFullscreen}
                        className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
                        title="Fullscreen"
                    >
                        <Maximize2 size={16} />
                    </button>
                    <button
                        onClick={onClose}
                        className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-700 hover:text-white transition-colors"
                        title="Close"
                    >
                        <X size={16} />
                    </button>
                </div>
            </div>

            {/* Viewer Content */}
            <div className="flex-1 relative overflow-auto bg-slate-950 flex items-center justify-center p-4 group">
                <div className="relative shadow-2xl">
                    <img
                        src={imageUrl}
                        alt={`Document Page ${page}`}
                        className="max-w-full h-auto block"
                        style={{ minWidth: '300px' }}
                    />

                    <svg
                        viewBox={`0 0 ${page_width} ${page_height}`}
                        className="absolute inset-0 w-full h-full pointer-events-none"
                    >
                        {instances.map((inst, idx) => (
                            <g key={idx}>
                                <polygon
                                    points={formatPoints(inst.polygon)}
                                    fill="none"
                                    stroke={getColor(inst.confidence)}
                                    strokeWidth="2"
                                    vectorEffect="non-scaling-stroke"
                                    strokeLinejoin="miter"
                                    className="animate-pulse"
                                />
                            </g>
                        ))}
                    </svg>

                    {/* Tooltip for first instance or group */}
                    {instances.length > 0 && (
                        <div
                            className="absolute hidden group-hover:flex items-center gap-2 px-2 py-1 bg-black/80 backdrop-blur-md rounded-lg text-[10px] font-bold text-white shadow-xl border border-white/10"
                            style={{
                                left: `${(instances[0].polygon[0] / page_width) * 100}%`,
                                top: `${(instances[0].polygon[1] / page_height) * 100}%`,
                                transform: 'translateY(-120%)'
                            }}
                        >
                            <AlertCircle size={10} style={{ color: footerColor }} />
                            <span>{(minConfidence * 100).toFixed(0)}% Min Confidence</span>
                        </div>
                    )}
                </div>
            </div>

            {/* Footer */}
            <div className="px-4 py-2 bg-slate-800 border-t border-slate-700 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: footerColor }}></div>
                        <span className="text-[10px] uppercase font-black text-slate-300 tracking-wider">
                            {minConfidence > 0.85 ? 'High' : minConfidence > 0.5 ? 'Medium' : 'Low'} Accuracy
                        </span>
                    </div>
                </div>
                <span className="text-[10px] font-mono text-slate-500">
                    Source: DocIntel (v2023-07-31)
                </span>
            </div>
        </div>
    );
};
