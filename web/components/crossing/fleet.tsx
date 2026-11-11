"use client";

import { DropdownMenu } from "@astryxdesign/core/DropdownMenu";
import { Text } from "@astryxdesign/core/Text";
import type { CarSnap, Snapshot } from "@/lib/types";

const FLEET_SIZES = [4, 8, 12, 16, 24];

export function CarsMenu({
  snap,
  selectedId,
  onSelect,
  send,
}: {
  snap: Snapshot;
  selectedId: string | null;
  onSelect: (id: string) => void;
  send: (message: Record<string, unknown>) => void;
}) {
  const live = snap.cars.filter((car) => !car.arrived);
  const stats = snap.stats
    ? `Arrivals ${snap.stats.arrivals} · crashes ${snap.stats.crashes} · ped hits ${snap.stats.ped_hits}${snap.wet ? " · wet" : ""}`
    : null;

  return (
    <DropdownMenu
      button={{ label: "Cars", size: "sm", variant: "ghost" }}
      menuWidth={280}
      menuMaxHeight={420}
      footer={stats ? <Text color="secondary">{stats}</Text> : undefined}
      items={[
        {
          type: "section",
          title: live.length ? `${live.length} driving` : "No cars on the road",
          items: live.length
            ? live.map((car: CarSnap) => ({
                id: car.id,
                label: car.name,
                description: `${car.from ?? "?"} → ${car.to ?? "?"} · ${car.speed.toFixed(0)} m/s`,
                onClick: () => onSelect(car.id),
                endContent: car.id === selectedId ? <Text color="secondary">Selected</Text> : undefined,
              }))
            : [{ label: "None on the road", isDisabled: true }],
        },
        { type: "divider" },
        {
          type: "section",
          title: "Fleet size",
          items: FLEET_SIZES.map((n) => ({
            label: String(n),
            description: snap.fleet?.size === n ? "Current" : undefined,
            onClick: () => send({ op: "fleet_size", value: n }),
          })),
        },
      ]}
    />
  );
}
