import React, { memo, useMemo } from 'react';
import { Sankey, Tooltip, ResponsiveContainer, Layer, Rectangle } from 'recharts';
// @ts-ignore
import { useChartWidth } from 'recharts';

interface SankeyNodeProps {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    payload?: any;
}

const CustomNode = memo((props: SankeyNodeProps) => {
    const { x, y, width, height, payload } = props;

    // Protect against invalid layout values
    if (
        x == null ||
        y == null ||
        width == null ||
        height == null ||
        isNaN(x) ||
        isNaN(y) ||
        isNaN(width) ||
        isNaN(height)
    ) {
        return null;
    }

    let containerWidth = 800;
    try {
        containerWidth = useChartWidth();
    } catch {
        // use default fallback
    }

    const isOut = x + width + 6 > containerWidth;

    return (
        <Layer>
            <Rectangle
                x={x}
                y={y}
                width={width}
                height={Math.max(height, 1)}
                fill={payload.color || '#4f46e5'}
                radius={2}
            />

            <text
                textAnchor={isOut ? "end" : "start"}
                x={isOut ? x - 6 : x + width + 6}
                y={y + height / 2}
                fontSize="14"
                fontWeight="bold"
                fill="#334155" // slate-700
            >
                {payload.name}
            </text>

            <text
                textAnchor={isOut ? "end" : "start"}
                x={isOut ? x - 6 : x + width + 6}
                y={y + height / 2 + 16}
                fontSize="12"
                fontWeight="600"
                fill="#64748b" // slate-500
            >
                {payload.value ?? 0}
            </text>
        </Layer>
    );
});
CustomNode.displayName = "CustomNode";

const CustomLink = memo((props: any) => {
    const { sourceX, sourceY, targetX, targetY, linkWidth } = props;
    const curvature = 0.4;
    const dx = targetX - sourceX;

    return (
        <path
            d={`
                M${sourceX},${sourceY}
                C${sourceX + dx * curvature},${sourceY}
                 ${targetX - dx * curvature},${targetY}
                 ${targetX},${targetY}
            `}
            stroke="#c7d2fe" // indigo-200
            strokeWidth={Math.max(linkWidth, 1)}
            fill="none"
            strokeOpacity={0.6}
            className="transition-all duration-300 hover:stroke-indigo-400 hover:stroke-opacity-100"
        />
    );
});
CustomLink.displayName = "CustomLink";

const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;

    const data = payload[0].payload;

    if (data.source && data.target) {
        return (
            <div className="bg-white shadow-xl p-3 border border-slate-100 rounded-xl">
                <strong className="text-slate-800 text-sm">
                    {data.source.name} → {data.target.name}
                </strong>
                <div className="text-indigo-600 font-bold mt-1">Volume: {data.value}</div>
            </div>
        );
    }

    return (
        <div className="bg-white shadow-xl p-3 border border-slate-100 rounded-xl">
            <strong className="text-slate-800 text-sm">{data.name}</strong>
            <div className="text-indigo-600 font-bold mt-1">Total: {data.value || "-"}</div>
        </div>
    );
};

interface SankeyChartProps {
    data: any;
    height?: number;
    nodeWidth?: number;
    nodePadding?: number;
    loading?: boolean;
    className?: string;
}

export const SankeyChart = memo(({
    data,
    height = 400,
    nodeWidth = 14,
    nodePadding = 50,
    loading = false,
    className,
}: SankeyChartProps) => {

    const sanitizedData = useMemo(() => {
        if (!data?.nodes?.length || !data?.links?.length) {
            return { nodes: [], links: [] };
        }

        // Add colors to nodes if MISSING to prevent crash/white boxes
        const colorPalette = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316', '#eab308', '#10b981', '#14b8a6', '#0ea5e9', '#3b82f6'];
        const coloredNodes = data.nodes.map((node: any, idx: number) => ({
            ...node,
            color: node.color || colorPalette[idx % colorPalette.length]
        }));

        return {
            nodes: coloredNodes,
            links: data.links.filter((link: any) => link.value > 0)
        };
    }, [data]);

    if (loading) {
        return (
            <div style={{ height }} className="flex items-center justify-center text-slate-400 font-medium">
                <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    Loading pipeline graph...
                </div>
            </div>
        );
    }

    if (!sanitizedData.nodes.length) {
        return (
            <div style={{ height }} className="flex items-center justify-center text-slate-400 font-medium">
                No pipeline data available to generate graph.
            </div>
        );
    }

    return (
        <div className={className} style={{ width: "100%", height, paddingRight: '20px' }}>
            <ResponsiveContainer>
                <Sankey
                    data={sanitizedData}
                    nodeWidth={nodeWidth}
                    nodePadding={nodePadding}
                    iterations={32}
                    nodeAlign="left"
                    link={<CustomLink />}
                    node={<CustomNode />}
                    margin={{ top: 20, bottom: 20, left: 20, right: 100 }}
                >
                    <Tooltip content={<CustomTooltip />} />
                </Sankey>
            </ResponsiveContainer>
        </div>
    );
});
SankeyChart.displayName = "SankeyChart";
