"use client";

import type { CarSnap } from "@/lib/types";

const LABELS: Record<string, string> = {
  LANE_LEFT: "Left",
  IDLE: "Hold",
  LANE_RIGHT: "Right",
  FASTER: "Faster",
  SLOWER: "Slower",
  STALLED: "Stalled",
  CRASHED: "Crashed",
};

export function Fleet({
  cars,
  selectedId,
  onSelect,
}: {
  cars: CarSnap[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex gap-2 overflow-x-auto px-3 py-2">
      {cars.map((car) => {
        const selected = car.id === selectedId;
        return (
          <button
            key={car.id}
            type="button"
            onClick={() => onSelect(car.id)}
            className="flex min-w-[148px] items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left"
            style={selected ? { borderColor: car.color } : undefined}
          >
            <span className="size-2.5 shrink-0 rounded-full" style={{ background: car.color }} />
            <span className="min-w-0">
              <span className="block text-xs font-medium">{car.name}</span>
              <span className="block font-mono text-[10px] text-muted-foreground">
                {car.speed.toFixed(1)} m/s · {LABELS[car.decision.meta_action] ?? car.decision.meta_action}
              </span>
            </span>
          </button>
        );
      })}
    </div>
  );
}
