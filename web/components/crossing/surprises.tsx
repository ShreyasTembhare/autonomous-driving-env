"use client";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Snapshot } from "@/lib/types";

const APPROACHES = ["north", "south", "east", "west"] as const;

type Props = {
  snap: Snapshot;
  selectedId: string | null;
  send: (message: Record<string, unknown>) => void;
};

export function SurprisePanel({ snap, selectedId, send }: Props) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b px-3 py-3">
        <h2 className="text-sm font-medium">Surprises</h2>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">
          These change the running town. Nothing resets until you ask.
        </p>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-4 p-3">
          <div>
            <div className="mb-2 text-[11px] tracking-wide text-muted-foreground uppercase">
              Signal
            </div>
            <div className="mb-2 grid grid-cols-2 gap-1.5">
              {APPROACHES.map((approach) => (
                <div
                  key={approach}
                  className="flex items-center justify-between rounded-md border px-2 py-1.5 text-xs"
                >
                  <span className="capitalize">{approach}</span>
                  <Lamp color={snap.signal.approaches[approach]} />
                </div>
              ))}
            </div>
            <p className="mb-2 text-xs text-muted-foreground">
              {snap.signal.label} · {snap.signal.remaining.toFixed(1)}s
            </p>
            <div className="flex flex-wrap gap-1.5">
              <Button size="sm" variant="secondary" onClick={() => send({ op: "flip" })}>
                Flip
              </Button>
              <Button size="sm" variant="secondary" onClick={() => send({ op: "all_red" })}>
                All-red
              </Button>
              <Button size="sm" variant="outline" onClick={() => send({ op: "restore" })}>
                Restore
              </Button>
            </div>
          </div>
          <div>
            <div className="mb-2 text-[11px] tracking-wide text-muted-foreground uppercase">
              The street
            </div>
            <div className="flex flex-wrap gap-1.5">
              <Button size="sm" variant="secondary" onClick={() => send({ op: "jaywalk" })}>
                Jaywalk
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => send({ op: "stall", car: selectedId })}
              >
                Stall
              </Button>
              <Button size="sm" variant="secondary" onClick={() => send({ op: "cut_in" })}>
                Cut-in
              </Button>
              <Button
                size="sm"
                variant={snap.wet ? "default" : "outline"}
                onClick={() => send({ op: "wet", on: !snap.wet })}
              >
                {snap.wet ? "Wet pavement" : "Dry pavement"}
              </Button>
            </div>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">
              {selectedId
                ? "Stall stops the selected car in its lane."
                : "Stall stops whoever is closest to the line. Cut-in sends Jules into Ada’s lane when he can."}
            </p>
          </div>
          <div>
            <div className="mb-2 text-[11px] tracking-wide text-muted-foreground uppercase">
              What happened
            </div>
            {snap.log.length === 0 ? (
              <p className="text-xs leading-5 text-muted-foreground">
                Nothing yet. The cycle is running on its own.
              </p>
            ) : (
              <ul className="space-y-1.5">
                {snap.log.map((row) => (
                  <li
                    key={`${row.index}-${row.tick}`}
                    className="flex items-center justify-between gap-2 rounded-md border px-2 py-1.5"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-xs">{row.label}</div>
                      <div className="font-mono text-[10px] text-muted-foreground">{row.time.toFixed(1)}s</div>
                    </div>
                    <Button size="xs" variant="ghost" onClick={() => send({ op: "replay", index: row.index })}>
                      Replay
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </ScrollArea>
    </div>
  );
}

function Lamp({ color }: { color: string }) {
  const paint = color === "green" ? "#22c55e" : color === "yellow" ? "#facc15" : "#ef4444";
  return <span className="inline-block size-2.5 rounded-full" style={{ background: paint }} />;
}
