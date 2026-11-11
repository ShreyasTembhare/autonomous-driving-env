"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { CarSnap, NetworkMap, Snapshot } from "@/lib/types";

const DEFAULT_EXTENT = 400;
const MIN_EXTENT = 60;
const MAX_EXTENT = 900;
const HIT_PX = 18;
const DRAG_PX = 5;

type View = { extent: number; cx: number; cy: number };
const HOME: View = { extent: DEFAULT_EXTENT, cx: 0, cy: 0 };

type Props = {
  snap: Snapshot;
  network: NetworkMap | null;
  selectedId: string | null;
  hoverPathKey: string | null;
  follow: boolean;
  previewPoints?: [number, number][] | null;
  tripPicking?: boolean;
  onSelect: (id: string | null) => void;
  onSelectNode?: (node: string | null) => void;
  onMapClick?: (x: number, y: number) => void;
  onFit?: () => void;
};

const clamp = (value: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, value));

function panBox(network: NetworkMap | null) {
  if (!network) return { xmin: -400, xmax: 400, ymin: -400, ymax: 400 };
  return {
    xmin: network.bounds.min[0],
    xmax: network.bounds.max[0],
    ymin: network.bounds.min[1],
    ymax: network.bounds.max[1],
  };
}

function fitFromNetwork(network: NetworkMap | null): View {
  if (!network) return HOME;
  const [[xmin, ymin], [xmax, ymax]] = [network.bounds.min, network.bounds.max];
  const span = Math.max(xmax - xmin, ymax - ymin) * 1.15;
  return { extent: clamp(span, MIN_EXTENT, MAX_EXTENT), cx: (xmin + xmax) / 2, cy: (ymin + ymax) / 2 };
}

export function CrossingCanvas({
  snap,
  network,
  selectedId,
  hoverPathKey,
  follow,
  previewPoints,
  tripPicking,
  onSelect,
  onSelectNode,
  onMapClick,
}: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>(HOME);
  const [hoverTip, setHoverTip] = useState<{ x: number; y: number; text: string; id: string } | null>(null);
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;

  const zoomBy = useCallback((factor: number, around?: { x: number; y: number }) => {
    setView((v) => {
      const next = clamp(v.extent * factor, MIN_EXTENT, MAX_EXTENT);
      const box = panBox(network);
      if (!around || !wrap.current) return { ...v, extent: next, cx: clamp(v.cx, box.xmin, box.xmax), cy: clamp(v.cy, box.ymin, box.ymax) };
      const parent = wrap.current;
      const scale = Math.min(parent.clientWidth, parent.clientHeight) / v.extent;
      const wx = v.cx + (around.x - parent.clientWidth / 2) / scale;
      const wy = v.cy - (around.y - parent.clientHeight / 2) / scale;
      const nscale = Math.min(parent.clientWidth, parent.clientHeight) / next;
      return {
        extent: next,
        cx: clamp(wx - (around.x - parent.clientWidth / 2) / nscale, box.xmin, box.xmax),
        cy: clamp(wy + (around.y - parent.clientHeight / 2) / nscale, box.ymin, box.ymax),
      };
    });
  }, [network]);

  const fitView = useCallback(() => {
    setView(fitFromNetwork(network));
  }, [network]);

  useEffect(() => {
    if (network) fitView();
  }, [network, fitView]);

  useEffect(() => {
    if (!follow || !selectedId) return;
    const car = snap.cars.find((c) => c.id === selectedId);
    if (!car) return;
    setView((v) => ({ ...v, cx: car.x, cy: car.y }));
  }, [follow, selectedId, snap.cars]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      zoomBy(event.deltaY > 0 ? 1.1 : 1 / 1.1, {
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      });
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [zoomBy]);

  useEffect(() => {
    const canvas = ref.current;
    const parent = wrap.current;
    if (!canvas || !parent) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const draw = () => {
      const width = parent.clientWidth;
      const height = parent.clientHeight;
      if (width < 2 || height < 2) return;
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const scale = Math.min(width, height) / view.extent;
      const toX = (x: number) => width / 2 + (x - view.cx) * scale;
      const toY = (y: number) => height / 2 - (y - view.cy) * scale;
      const half = network?.road_half ?? 7;

      ctx.fillStyle = "#3a424e";
      ctx.fillRect(0, 0, width, height);

      if (network) {
        ctx.fillStyle = "#2c333c";
        for (const block of network.blocks ?? []) {
          const [ax, ay] = block.a;
          const [bx, by] = block.b;
          ctx.fillRect(toX(ax), toY(by), (bx - ax) * scale, (by - ay) * scale);
        }

        ctx.fillStyle = "#2a313a";
        for (const road of network.roads) {
          const dx = road.b[0] - road.a[0];
          const dy = road.b[1] - road.a[1];
          const len = Math.hypot(dx, dy) || 1;
          const nx = (-dy / len) * half;
          const ny = (dx / len) * half;
          ctx.beginPath();
          ctx.moveTo(toX(road.a[0] + nx), toY(road.a[1] + ny));
          ctx.lineTo(toX(road.b[0] + nx), toY(road.b[1] + ny));
          ctx.lineTo(toX(road.b[0] - nx), toY(road.b[1] - ny));
          ctx.lineTo(toX(road.a[0] - nx), toY(road.a[1] - ny));
          ctx.closePath();
          ctx.fill();
        }
        for (const node of network.intersections) {
          ctx.fillRect(toX(node.x - half), toY(node.y + half), half * 2 * scale, half * 2 * scale);
        }

        ctx.strokeStyle = "#c6a13a";
        ctx.lineWidth = 1.5;
        for (const road of network.roads) {
          ctx.beginPath();
          ctx.moveTo(toX(road.a[0]), toY(road.a[1]));
          ctx.lineTo(toX(road.b[0]), toY(road.b[1]));
          ctx.stroke();
        }

        ctx.strokeStyle = "rgba(232, 236, 242, 0.85)";
        ctx.lineWidth = 2;
        for (const line of network.stop_lines) {
          ctx.beginPath();
          ctx.moveTo(toX(line.a[0]), toY(line.a[1]));
          ctx.lineTo(toX(line.b[0]), toY(line.b[1]));
          ctx.stroke();
        }

        for (const cw of network.crosswalks) {
          paintCrosswalk(ctx, toX, toY, cw.a, cw.b, scale);
        }

        ctx.fillStyle = "rgba(232, 236, 242, 0.55)";
        ctx.font = "600 11px var(--font-geist-sans), sans-serif";
        ctx.textAlign = "center";
        for (const stub of network.stubs) {
          ctx.fillText(stub.name, toX(stub.x), toY(stub.y));
        }

        for (const road of network.roads) {
          if (road.name) paintStreetName(ctx, toX, toY, road, scale);
        }
      }

      const selected = snap.cars.find((car) => car.id === selectedId) ?? null;
      const seen = new Set(selected?.decision.seen.map((row) => row.id) ?? []);

      for (const car of snap.cars) {
        const pts = car.decision.route?.points;
        if (!pts || pts.length < 2) continue;
        ctx.beginPath();
        pts.forEach(([x, y], i) => {
          if (i === 0) ctx.moveTo(toX(x), toY(y));
          else ctx.lineTo(toX(x), toY(y));
        });
        ctx.strokeStyle = car.id === selectedId ? hexAlpha(car.color, 0.85) : hexAlpha(car.color, 0.28);
        ctx.lineWidth = car.id === selectedId ? 2.5 : 1.5;
        ctx.stroke();
        if (car.dest) {
          const [bx, by] = car.dest;
          ctx.fillStyle = car.color;
          ctx.beginPath();
          ctx.arc(toX(bx), toY(by), 4, 0, Math.PI * 2);
          ctx.fill();
          ctx.fillStyle = "#f8fafc";
          ctx.font = "700 10px var(--font-geist-sans), sans-serif";
          ctx.fillText("B", toX(bx), toY(by) - 8);
        }
      }

      if (previewPoints && previewPoints.length > 1) {
        ctx.setLineDash([6, 5]);
        ctx.strokeStyle = "#22d3ee";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        previewPoints.forEach(([x, y], i) => {
          if (i === 0) ctx.moveTo(toX(x), toY(y));
          else ctx.lineTo(toX(x), toY(y));
        });
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (selected?.decision.candidates) {
        for (const cand of selected.decision.candidates) {
          if (!cand.path?.length) continue;
          const active = cand.chosen || cand.key === hoverPathKey;
          if (!active && !cand.chosen) {
            if (cand.key !== hoverPathKey) continue;
          }
          ctx.setLineDash(cand.chosen ? [] : [5, 5]);
          ctx.strokeStyle = cand.chosen
            ? hexAlpha(selected.color, 0.95)
            : "rgba(248, 250, 252, 0.55)";
          ctx.lineWidth = cand.chosen ? 2.5 : 1.5;
          ctx.beginPath();
          cand.path.forEach(([x, y], i) => {
            if (i === 0) ctx.moveTo(toX(x), toY(y));
            else ctx.lineTo(toX(x), toY(y));
          });
          ctx.stroke();
          ctx.setLineDash([]);
          if (cand.key === hoverPathKey) {
            const tip = cand.path[Math.min(4, cand.path.length - 1)];
            ctx.fillStyle = "#f8fafc";
            ctx.font = "600 11px var(--font-geist-sans), sans-serif";
            ctx.fillText(`${cand.label} · ${cand.total.toFixed(1)}`, toX(tip[0]), toY(tip[1]) - 6);
          }
        }
      }

      if (selected?.decision.stop_point) {
        const sp = selected.decision.stop_point;
        ctx.strokeStyle = "#facc15";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(toX(sp.x), toY(sp.y), 6, 0, Math.PI * 2);
        ctx.stroke();
      }

      if (selected?.decision.idm?.leader?.kind === "car" && selected.decision.idm.leader.id) {
        const lead = snap.cars.find((c) => c.id === selected.decision.idm?.leader?.id);
        if (lead) {
          ctx.strokeStyle = "#fb923c";
          ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.arc(toX(lead.x), toY(lead.y), 14, 0, Math.PI * 2);
          ctx.stroke();
        }
      }

      for (const ped of snap.pedestrians) {
        if (ped.kind !== "jaywalker" || ped.path.length < 2) continue;
        ctx.save();
        ctx.setLineDash([5, 6]);
        ctx.strokeStyle = "rgba(250, 204, 21, 0.85)";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ped.path.forEach(([x, y], index) => {
          const px = toX(x);
          const py = toY(y);
          if (index === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.stroke();
        ctx.restore();
      }

      for (const ped of snap.pedestrians) {
        drawPed(ctx, toX(ped.x), toY(ped.y), ped.kind === "jaywalker", ped.hit, seen.has(ped.id));
      }

      for (const car of snap.cars) {
        if (car.arrived) continue;
        drawCar(
          ctx,
          car,
          toX,
          toY,
          scale,
          car.id === selectedId,
          seen.has(car.id),
          car.id === hoverTip?.id,
        );
      }

      for (const sig of snap.signals) {
        for (const lamp of sig.lamps) {
          drawLamp(ctx, toX(lamp.x), toY(lamp.y), lamp.color);
        }
      }
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [snap, selectedId, view, network, hoverPathKey, previewPoints, hoverTip?.id]);

  const worldAt = (clientX: number, clientY: number) => {
    const canvas = ref.current;
    const parent = wrap.current;
    if (!canvas || !parent) return null;
    const rect = canvas.getBoundingClientRect();
    const scale = Math.min(parent.clientWidth, parent.clientHeight) / view.extent;
    const px = clientX - rect.left;
    const py = clientY - rect.top;
    return {
      x: view.cx + (px - parent.clientWidth / 2) / scale,
      y: view.cy - (py - parent.clientHeight / 2) / scale,
      px,
      py,
    };
  };

  const pickCar = (clientX: number, clientY: number): CarSnap | null => {
    const parent = wrap.current;
    const at = worldAt(clientX, clientY);
    if (!parent || !at) return null;
    const scale = Math.min(parent.clientWidth, parent.clientHeight) / view.extent;
    let best: CarSnap | null = null;
    let bestDist = Infinity;
    for (const car of snap.cars) {
      if (car.arrived) continue;
      const cx = parent.clientWidth / 2 + (car.x - view.cx) * scale;
      const cy = parent.clientHeight / 2 - (car.y - view.cy) * scale;
      const dx = at.px - cx;
      const dy = at.py - cy;
      const dist = Math.hypot(dx, dy);
      const cos = Math.cos(car.heading);
      const sin = Math.sin(car.heading);
      const along = dx * cos - dy * sin;
      const across = dx * sin + dy * cos;
      const inRect =
        Math.abs(along) <= (car.length * scale) / 2 + 6 && Math.abs(across) <= (car.width * scale) / 2 + 6;
      if ((inRect || dist <= HIT_PX) && dist < bestDist) {
        best = car;
        bestDist = dist;
      }
    }
    return best;
  };

  const pickNode = (clientX: number, clientY: number) => {
    if (!network) return null;
    const at = worldAt(clientX, clientY);
    if (!at) return null;
    let best: string | null = null;
    let bestDist = Infinity;
    for (const node of network.intersections) {
      const d = Math.hypot(at.x - node.x, at.y - node.y);
      if (d < 14 && d < bestDist) {
        best = node.id;
        bestDist = d;
      }
    }
    for (const sig of snap.signals) {
      for (const lamp of sig.lamps) {
        const d = Math.hypot(at.x - lamp.x, at.y - lamp.y);
        if (d < 8 && d < bestDist) {
          best = sig.node;
          bestDist = d;
        }
      }
    }
    return best;
  };

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
    drag.current = { x: event.clientX, y: event.clientY, cx: view.cx, cy: view.cy, moved: false };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const start = drag.current;
    const parent = wrap.current;
    if (start && parent) {
      const dx = event.clientX - start.x;
      const dy = event.clientY - start.y;
      if (start.moved || Math.hypot(dx, dy) >= DRAG_PX) {
        start.moved = true;
        const scale = Math.min(parent.clientWidth, parent.clientHeight) / view.extent;
        const box = panBox(network);
        setView((v) => ({
          ...v,
          cx: clamp(start.cx - dx / scale, box.xmin, box.xmax),
          cy: clamp(start.cy + dy / scale, box.ymin, box.ymax),
        }));
        return;
      }
    }
    const car = pickCar(event.clientX, event.clientY);
    if (car) {
      const rect = ref.current?.getBoundingClientRect();
      setHoverTip({
        id: car.id,
        x: event.clientX - (rect?.left ?? 0) + 12,
        y: event.clientY - (rect?.top ?? 0) + 12,
        text: `${car.name} · ${car.from ?? "?"} → ${car.to ?? "?"} · ${car.speed.toFixed(1)} m/s`,
      });
    } else {
      setHoverTip(null);
    }
  };

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const start = drag.current;
    drag.current = null;
    if (!start || start.moved) return;
    if (event.detail === 2) {
      const car = pickCar(event.clientX, event.clientY);
      if (car) {
        setView((v) => ({ ...v, extent: clamp(v.extent * 0.55, MIN_EXTENT, MAX_EXTENT), cx: car.x, cy: car.y }));
        onSelect(car.id);
        return;
      }
    }
    if (tripPicking && onMapClick) {
      const at = worldAt(event.clientX, event.clientY);
      if (at) {
        onMapClick(at.x, at.y);
        return;
      }
    }
    const car = pickCar(event.clientX, event.clientY);
    if (car) {
      onSelect(car.id);
      return;
    }
    const node = pickNode(event.clientX, event.clientY);
    if (node) {
      onSelectNode?.(node);
      onSelect(null);
      return;
    }
    onSelect(null);
  };

  const fitted = fitFromNetwork(network);
  const atHome =
    Math.abs(view.extent - fitted.extent) < 1 && Math.abs(view.cx - fitted.cx) < 1 && Math.abs(view.cy - fitted.cy) < 1;

  return (
    <VStack ref={wrap} height="100%" width="100%" minHeight={240} className="relative">
      <canvas
        ref={ref}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => setHoverTip(null)}
        onPointerCancel={() => {
          drag.current = null;
        }}
        className={`block h-full w-full touch-none ${tripPicking ? "cursor-crosshair" : "cursor-grab active:cursor-grabbing"}`}
      />
      {hoverTip ? (
        <Text
          color="secondary"
          className="pointer-events-none absolute z-20 max-w-xs rounded-md border border-border bg-surface px-2 py-1 shadow-md"
          style={{ left: hoverTip.x, top: hoverTip.y }}
        >
          {hoverTip.text}
        </Text>
      ) : null}
      <HStack gap={1} className="absolute right-4 bottom-4">
        <Button label="−" size="sm" variant="ghost" tooltip="Zoom out" onClick={() => zoomBy(1.25)} />
        <Button label="+" size="sm" variant="ghost" tooltip="Zoom in" onClick={() => zoomBy(1 / 1.25)} />
        <Button label="Fit" size="sm" variant="ghost" isDisabled={atHome} onClick={fitView} />
      </HStack>
    </VStack>
  );
}

function paintStreetName(
  ctx: CanvasRenderingContext2D,
  toX: (x: number) => number,
  toY: (y: number) => number,
  road: { a: [number, number]; b: [number, number]; name?: string },
  scale: number,
) {
  if (!road.name || scale < 0.55) return;
  const mx = (road.a[0] + road.b[0]) / 2;
  const my = (road.a[1] + road.b[1]) / 2;
  const dx = road.b[0] - road.a[0];
  const dy = road.b[1] - road.a[1];
  let angle = Math.atan2(-(dy), dx);
  if (angle > Math.PI / 2) angle -= Math.PI;
  if (angle < -Math.PI / 2) angle += Math.PI;
  ctx.save();
  ctx.translate(toX(mx), toY(my));
  ctx.rotate(angle);
  ctx.fillStyle = "rgba(232, 236, 242, 0.5)";
  ctx.font = `600 ${Math.max(10, Math.min(14, 11 * scale))}px var(--font-geist-sans), sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(road.name, 0, -10);
  ctx.restore();
}

function paintCrosswalk(
  ctx: CanvasRenderingContext2D,
  toX: (x: number) => number,
  toY: (y: number) => number,
  a: [number, number],
  b: [number, number],
  scale: number,
) {
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const nx = -uy;
  const ny = ux;
  ctx.fillStyle = "rgba(232, 236, 242, 0.72)";
  for (let i = 0; i < 6; i += 1) {
    const t = (i + 0.5) / 6;
    const cx = a[0] + dx * t;
    const cy = a[1] + dy * t;
    const hw = 0.9;
    const hl = 0.35;
    ctx.beginPath();
    ctx.moveTo(toX(cx + ux * hl + nx * hw), toY(cy + uy * hl + ny * hw));
    ctx.lineTo(toX(cx - ux * hl + nx * hw), toY(cy - uy * hl + ny * hw));
    ctx.lineTo(toX(cx - ux * hl - nx * hw), toY(cy - uy * hl - ny * hw));
    ctx.lineTo(toX(cx + ux * hl - nx * hw), toY(cy + uy * hl - ny * hw));
    ctx.closePath();
    ctx.fill();
  }
  void scale;
}

function drawCar(
  ctx: CanvasRenderingContext2D,
  car: CarSnap,
  toX: (x: number) => number,
  toY: (y: number) => number,
  scale: number,
  selected: boolean,
  seen: boolean,
  hovered: boolean,
) {
  const px = toX(car.x);
  const py = toY(car.y);
  ctx.save();
  ctx.translate(px, py);
  ctx.rotate(-car.heading);
  const length = car.length * scale;
  const width = car.width * scale;
  roundRect(ctx, -length / 2, -width / 2, length, width, 4);
  ctx.fillStyle = car.crashed ? "#6b7280" : car.color;
  ctx.fill();
  if (seen || selected) {
    ctx.lineWidth = selected ? 2.5 : 2;
    ctx.strokeStyle = "#f8fafc";
    ctx.stroke();
  }
  if (car.indicator === "left" || car.indicator === "right") {
    const blink = Math.floor(Date.now() / 350) % 2 === 0;
    if (blink) {
      ctx.fillStyle = "#facc15";
      const side = car.indicator === "left" ? -1 : 1;
      ctx.beginPath();
      ctx.arc(length * 0.35, side * width * 0.45, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }
  }
  ctx.fillStyle = "rgba(15, 18, 24, 0.55)";
  ctx.fillRect(length * 0.12, -width * 0.32, length * 0.22, width * 0.64);
  ctx.restore();

  if (selected) {
    ctx.beginPath();
    ctx.arc(px, py, Math.max(length, width) * 0.72, 0, Math.PI * 2);
    ctx.strokeStyle = "#f8fafc";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }

  if (selected || hovered) {
    ctx.font = "600 12px var(--font-geist-sans), sans-serif";
    ctx.fillStyle = "#f8fafc";
    ctx.textAlign = "center";
    ctx.fillText(car.name, px, py + Math.max(length, width) / 2 + 13);
  }
}

function drawPed(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  jay: boolean,
  hit: boolean,
  seen: boolean,
) {
  ctx.save();
  ctx.fillStyle = hit ? "#9ca3af" : jay ? "#facc15" : "#f4efe4";
  ctx.beginPath();
  ctx.arc(x, y, 5.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(x, y - 7, 3, 0, Math.PI * 2);
  ctx.fill();
  if (seen) {
    ctx.strokeStyle = "#f8fafc";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(x, y - 2, 10, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function drawLamp(ctx: CanvasRenderingContext2D, x: number, y: number, color: string) {
  ctx.save();
  ctx.fillStyle = "#111418";
  roundRect(ctx, x - 7, y - 18, 14, 36, 3);
  ctx.fill();
  const colors = ["#ef4444", "#facc15", "#22c55e"];
  const active = color === "red" ? 0 : color === "yellow" ? 1 : 2;
  colors.forEach((lamp, index) => {
    ctx.beginPath();
    ctx.arc(x, y - 11 + index * 11, 3.8, 0, Math.PI * 2);
    ctx.fillStyle = index === active ? lamp : "#2a3038";
    ctx.fill();
  });
  ctx.restore();
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function hexAlpha(hex: string, alpha: number) {
  const value = hex.replace("#", "");
  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
