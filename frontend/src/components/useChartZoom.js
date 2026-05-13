// Reusable drag-to-zoom for Recharts charts that use a numeric X axis.
//
// Usage:
//   const zoom = useChartZoom();
//   <LineChart data={rows} {...zoom.chartProps}>
//     <XAxis dataKey="ts" type="number" domain={zoom.domain} ...
//     {zoom.refArea && <ReferenceArea x1={zoom.refArea.x1} x2={zoom.refArea.x2} ... />}
//   </LineChart>
//   {zoom.isZoomed && <button onClick={zoom.reset}>Reset zoom</button>}

import { useState } from "react";

export function useChartZoom({ minSpan = 0 } = {}) {
  const [domain, setDomain] = useState(null); // null = full data range
  const [dragStart, setDragStart] = useState(null);
  const [dragEnd, setDragEnd] = useState(null);
  // activePayload is the recharts payload under the cursor — used to render
  // a horizontal "crosshair" reference line at each visible series' value so
  // you can see where else in the chart that level is crossed.
  const [activePayload, setActivePayload] = useState(null);

  const chartProps = {
    onMouseDown: (e) => {
      if (e?.activeLabel != null) {
        setDragStart(e.activeLabel);
        setDragEnd(e.activeLabel);
      }
    },
    onMouseMove: (e) => {
      if (dragStart != null && e?.activeLabel != null) setDragEnd(e.activeLabel);
      if (e?.activePayload?.length) setActivePayload(e.activePayload);
      else setActivePayload(null);
    },
    onMouseUp: () => {
      if (dragStart != null && dragEnd != null && dragStart !== dragEnd) {
        const a = Math.min(dragStart, dragEnd);
        const b = Math.max(dragStart, dragEnd);
        if (b - a > minSpan) setDomain([a, b]);
      }
      setDragStart(null);
      setDragEnd(null);
    },
    onMouseLeave: () => {
      setDragStart(null);
      setDragEnd(null);
      setActivePayload(null);
    },
  };

  return {
    domain: domain || ["dataMin", "dataMax"],
    isZoomed: domain != null,
    chartProps,
    refArea:
      dragStart != null && dragEnd != null && dragStart !== dragEnd
        ? { x1: Math.min(dragStart, dragEnd), x2: Math.max(dragStart, dragEnd) }
        : null,
    // Caller renders one <ReferenceLine y={p.value} stroke={p.color} ...> per
    // entry. We expose dataKey so multi-axis charts can map back to yAxisId.
    crosshairs: (activePayload || [])
      .filter((p) => p.value != null && Number.isFinite(p.value))
      .map((p) => ({
        dataKey: p.dataKey,
        value: p.value,
        color: p.color || p.stroke,
      })),
    reset: () => setDomain(null),
  };
}
