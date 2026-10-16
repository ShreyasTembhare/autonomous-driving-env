"use client";

import { useEffect, useRef } from "react";
import type { CarSnap, Snapshot } from "@/lib/types";

const EXTENT = 120;

type Props = {
  snap: Snapshot;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
};

export function CrossingCanvas({ snap, selectedId, onSelect }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);

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

      const scale = Math.min(width, height) / EXTENT;
      const toX = (x: number) => width / 2 + x * scale;
      const toY = (y: number) => height / 2 - y * scale;
      const edge = snap.map.edge;
      const stop = snap.map.stop;
      const box = snap.map.box;

      ctx.fillStyle = "#3a424e";
      ctx.fillRect(0, 0, width, height);

      ctx.fillStyle = "#2a313a";
      ctx.fillRect(toX(-60), toY(edge), 120 * scale, edge * 2 * scale);
      ctx.fillRect(toX(-edge), toY(60), edge * 2 * scale, 120 * scale);

      ctx.strokeStyle = "#c6a13a";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(toX(-60), toY(0));
      ctx.lineTo(toX(-box), toY(0));
      ctx.moveTo(toX(box), toY(0));
      ctx.lineTo(toX(60), toY(0));
      ctx.moveTo(toX(0), toY(60));
      ctx.lineTo(toX(0), toY(box));
      ctx.moveTo(toX(0), toY(-box));
      ctx.lineTo(toX(0), toY(-60));
      ctx.stroke();

      ctx.strokeStyle = "rgba(232, 236, 242, 0.55)";
      ctx.lineWidth = 1;
      ctx.setLineDash([8, 10]);
      for (const lat of [-3.5, 3.5]) {
        ctx.beginPath();
        ctx.moveTo(toX(-60), toY(lat));
        ctx.lineTo(toX(-box), toY(lat));
        ctx.moveTo(toX(box), toY(lat));
        ctx.lineTo(toX(60), toY(lat));
        ctx.moveTo(toX(lat), toY(60));
        ctx.lineTo(toX(lat), toY(box));
        ctx.moveTo(toX(lat), toY(-box));
        ctx.lineTo(toX(lat), toY(-60));
        ctx.stroke();
      }
      ctx.setLineDash([]);

      ctx.strokeStyle = "rgba(232, 236, 242, 0.85)";
      ctx.lineWidth = 2;
      const stops: [number, number, number, number][] = [
        [-stop, -edge, -stop, edge],
        [stop, -edge, stop, edge],
        [-edge, -stop, edge, -stop],
        [-edge, stop, edge, stop],
      ];
      for (const [x1, y1, x2, y2] of stops) {
        ctx.beginPath();
        ctx.moveTo(toX(x1), toY(y1));
        ctx.lineTo(toX(x2), toY(y2));
        ctx.stroke();
      }

      const walk = snap.map.crosswalk ?? 8.6;
      paintCrosswalk(ctx, toX, toY, -walk, 0, true);
      paintCrosswalk(ctx, toX, toY, walk, 0, true);
      paintCrosswalk(ctx, toX, toY, 0, -walk, false);
      paintCrosswalk(ctx, toX, toY, 0, walk, false);

      const selected = snap.cars.find((car) => car.id === selectedId) ?? null;
      const seen = new Set(selected?.decision.seen.map((row) => row.id) ?? []);

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

      if (selected) {
        const px = toX(selected.x);
        const py = toY(selected.y);
        const range = selected.decision.cone.range * scale;
        const half = selected.decision.cone.half_angle;
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.arc(px, py, range, -selected.heading - half, -selected.heading + half);
        ctx.closePath();
        ctx.fillStyle = hexAlpha(selected.color, 0.16);
        ctx.fill();
        ctx.strokeStyle = hexAlpha(selected.color, 0.7);
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      for (const ped of snap.pedestrians) {
        drawPed(ctx, toX(ped.x), toY(ped.y), ped.kind === "jaywalker", ped.hit, seen.has(ped.id));
      }

      for (const car of snap.cars) {
        drawCar(ctx, car, toX, toY, scale, car.id === selectedId, seen.has(car.id));
      }

      for (const lamp of snap.signal.lamps) {
        drawLamp(ctx, toX(lamp.x), toY(lamp.y), lamp.color);
      }
    };

    draw();
    const observer = new ResizeObserver(draw);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [snap, selectedId]);

  const onPointer = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = ref.current;
    const parent = wrap.current;
    if (!canvas || !parent) return;
    const rect = canvas.getBoundingClientRect();
    const scale = Math.min(parent.clientWidth, parent.clientHeight) / EXTENT;
    const x = (event.clientX - rect.left - parent.clientWidth / 2) / scale;
    const y = (parent.clientHeight / 2 - (event.clientY - rect.top)) / scale;
    let best: CarSnap | null = null;
    let bestDist = 3.2;
    for (const car of snap.cars) {
      const dist = Math.hypot(car.x - x, car.y - y);
      if (dist < bestDist) {
        best = car;
        bestDist = dist;
      }
    }
    onSelect(best ? best.id : null);
  };

  return (
    <div ref={wrap} className="relative h-full min-h-[240px] w-full">
      <canvas ref={ref} onPointerDown={onPointer} className="block h-full w-full cursor-crosshair" />
    </div>
  );
}

function paintCrosswalk(
  ctx: CanvasRenderingContext2D,
  toX: (x: number) => number,
  toY: (y: number) => number,
  x: number,
  y: number,
  vertical: boolean,
) {
  ctx.save();
  ctx.fillStyle = "rgba(232, 236, 242, 0.78)";
  const stripes = 5;
  for (let i = 0; i < stripes; i += 1) {
    const offset = -2.0 + i * 1.0;
    if (vertical) {
      ctx.fillRect(toX(x - 0.35), toY(y + offset + 0.45), 0.7 * (toX(1) - toX(0)), 0.7 * (toY(0) - toY(1)));
    } else {
      ctx.fillRect(toX(x + offset - 0.35), toY(y + 0.35), 0.7 * (toX(1) - toX(0)), 0.7 * (toY(0) - toY(1)));
    }
  }
  ctx.restore();
}

function drawCar(
  ctx: CanvasRenderingContext2D,
  car: CarSnap,
  toX: (x: number) => number,
  toY: (y: number) => number,
  scale: number,
  selected: boolean,
  seen: boolean,
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
    ctx.strokeStyle = selected ? "#f8fafc" : "#f8fafc";
    ctx.stroke();
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

  ctx.font = "11px var(--font-geist-sans), sans-serif";
  ctx.fillStyle = "#f8fafc";
  ctx.textAlign = "center";
  ctx.fillText(car.name, px, py + width / 2 + 12);
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
  roundRect(ctx, x - 8, y - 22, 16, 44, 4);
  ctx.fill();
  const colors = ["#ef4444", "#facc15", "#22c55e"];
  const active = color === "red" ? 0 : color === "yellow" ? 1 : 2;
  colors.forEach((lamp, index) => {
    ctx.beginPath();
    ctx.arc(x, y - 14 + index * 14, 4.5, 0, Math.PI * 2);
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
