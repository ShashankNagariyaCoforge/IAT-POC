import React from 'react';
import { Maximize2, X, AlertCircle } from 'lucide-react';
import { ExtractionInstance } from '../types';

interface DocumentAnnotatorProps {
    caseId: string;
    instance: ExtractionInstance;
    onClose: () => void;
    onFullscreen: () => void;
}

export const DocumentAnnotator: React.FC<DocumentAnnotatorProps> = ({
    caseId,
    instance,
    onClose,
    onFullscreen
}) => {
    const { doc_id, page, polygon, confidence, page_width, page_height } = instance;

    // Determine color based on confidence
    const getColor = (conf: number) => {
        if (conf > 0.85) return '#10b981'; // emerald-500
        if (conf > 0.50) return '#f59e0b'; // amber-500
        return '#ef4444'; // red-500
    };

    const color = getColor(confidence);
    const imageUrl = `/api/cases/${caseId}/documents/${doc_id}/pages/${page}/image`;

    // Convert polygon to SVG points string
    // Polygon is [x1, y1, x2, y2, x3, y3, x4, y4]
    const formatPoints = () => {
        const points = [];
        for (let i = 0; i < polygon.length; i += 2) {
            // Scale points based on SVG viewbox (0 to page_width/height)
            points.push(`${polygon[i]},${polygon[i + 1]}`);
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
                {/* SVG Overlay Container */}
                <div className="relative shadow-2xl">
                    <img
                        src={imageUrl}
                        alt={`Document Page ${page}`}
                        className="max-w-full h-auto block"
                        style={{ minWidth: '300px' }}
                    />

                    {/* SVG Layer */}
                    <svg
                        viewBox={`0 0 ${page_width} ${page_height}`}
                        className="absolute inset-0 w-full h-full pointer-events-none"
                    >
                        {/* Highlighted Bounding Box */}
                        <polygon
                            points={formatPoints()}
                            fill={`${color}33`} // 20% opacity fill
                            stroke={color}
                            strokeWidth={2}
                            className="animate-pulse"
                        />
                    </svg>

                    {/* Confidence Indicator Tooltip */}
                    <div
                        className="absolute hidden group-hover:flex items-center gap-2 px-2 py-1 bg-black/80 backdrop-blur-md rounded-lg text-[10px] font-bold text-white shadow-xl border border-white/10"
                        style={{
                            left: `${(polygon[0] / page_width) * 100}%`,
                            top: `${(polygon[1] / page_height) * 100}%`,
                            transform: 'translateY(-120%)'
                        }}
                    >
                        <AlertCircle size={10} style={{ color }} />
                        <span>{(confidence * 100).toFixed(0)}% Confidence</span>
                    </div>
                </div>
            </div>

            {/* Footer / Status */}
            <div className="px-4 py-2 bg-slate-800 border-t border-slate-700 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }}></div>
                        <span className="text-[10px] uppercase font-black text-slate-300 tracking-wider">
                            {confidence > 0.85 ? 'High' : confidence > 0.5 ? 'Medium' : 'Low'} Accuracy
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
