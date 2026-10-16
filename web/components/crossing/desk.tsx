"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { CrossingCanvas } from "@/components/crossing/canvas-view";
import { Fleet } from "@/components/crossing/fleet";
import { Inspector } from "@/components/crossing/inspector";
import { SurprisePanel } from "@/components/crossing/surprises";
import { TrainView } from "@/components/crossing/train-view";
import { useSim } from "@/lib/use-sim";

const SPEEDS = [0.5, 1, 2, 4];

export function Desk() {
  const { status, snap, send, retry } = useSim();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"town" | "train">("town");
  const [surpriseOpen, setSurpriseOpen] = useState(false);
  const [inspectOpen, setInspectOpen] = useState(false);

  const cars = snap?.cars ?? [];
  const selected = cars.find((car) => car.id === selectedId) ?? null;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (!snap) return;
        send({ op: snap.paused ? "play" : "pause" });
      }
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        if (!cars.length) return;
        const index = Math.max(0, cars.findIndex((car) => car.id === selectedId));
        const next =
          event.key === "ArrowRight"
            ? cars[(index + 1) % cars.length]
            : cars[(index - 1 + cars.length) % cars.length];
        setSelectedId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cars, selectedId, send, snap]);

  return (
    <div className="dark flex h-dvh flex-col bg-background text-foreground">
      <header className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <div className="mr-2">
          <div className="text-sm font-medium">The crossing</div>
          <div className="text-[11px] text-muted-foreground">
            {snap ? snap.signal.label : "One intersection, six cars"}
          </div>
        </div>
        <Button
          size="sm"
          variant={view === "town" ? "secondary" : "ghost"}
          onClick={() => setView("town")}
        >
          Town
        </Button>
        <Button
          size="sm"
          variant={view === "train" ? "secondary" : "ghost"}
          onClick={() => setView("train")}
        >
          Train
        </Button>
        <div className="mx-1 hidden h-5 w-px bg-border sm:block" />
        <Button
          size="sm"
          disabled={!snap || status !== "open"}
          onClick={() => snap && send({ op: snap.paused ? "play" : "pause" })}
        >
          {snap?.paused ? "Play" : "Pause"}
        </Button>
        {SPEEDS.map((speed) => (
          <Button
            key={speed}
            size="sm"
            variant={snap?.speed === speed ? "secondary" : "outline"}
            onClick={() => send({ op: "speed", value: speed })}
          >
            {speed}×
          </Button>
        ))}
        <Button size="sm" variant="outline" onClick={() => send({ op: "reset" })}>
          Reset
        </Button>
        <div className="ml-auto flex items-center gap-2">
          <Status status={status} onRetry={retry} />
        </div>
      </header>

      {status === "connecting" && !snap ? (
        <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
          Connecting to the crossing…
        </div>
      ) : status === "error" && !snap ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="max-w-sm text-sm leading-6">
            The sim socket dropped. Start the Python server on port 43124, then retry.
          </p>
          <Button onClick={retry}>Retry</Button>
        </div>
      ) : view === "train" && snap ? (
        <TrainView train={snap.train} send={send} />
      ) : snap ? (
        <>
          <div className="flex gap-2 border-b px-3 py-2 md:hidden">
            <Button size="sm" variant="outline" onClick={() => setSurpriseOpen(true)}>
              Surprises
            </Button>
            <Button size="sm" variant="outline" onClick={() => setInspectOpen(true)}>
              Inspector
            </Button>
          </div>
          <div className="grid min-h-0 flex-1 md:grid-cols-[280px_minmax(0,1fr)_340px]">
            <aside className="hidden min-h-0 border-r md:block">
              <SurprisePanel snap={snap} selectedId={selectedId} send={send} />
            </aside>
            <main className="relative min-h-0">
              {status === "error" ? (
                <div className="absolute inset-x-0 top-2 z-10 mx-auto flex w-fit items-center gap-2 rounded-md border bg-popover px-3 py-2 text-xs">
                  The sim socket dropped.
                  <Button size="xs" onClick={retry}>
                    Retry
                  </Button>
                </div>
              ) : null}
              <CrossingCanvas snap={snap} selectedId={selectedId} onSelect={setSelectedId} />
              {snap.all_crashed ? (
                <div className="absolute inset-x-0 bottom-4 mx-auto w-[min(100%-2rem,28rem)] rounded-lg border bg-popover p-4 shadow-lg">
                  <p className="text-sm font-medium">Every car has crashed.</p>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    The crossing is stopped. Reset brings the six of them back to the start of their
                    routes.
                  </p>
                  <Button className="mt-3" size="sm" onClick={() => send({ op: "reset" })}>
                    Reset the town
                  </Button>
                </div>
              ) : null}
              {snap.paused && !snap.all_crashed ? (
                <div className="pointer-events-none absolute top-2 left-2 rounded-md border bg-popover px-2 py-1 text-[11px]">
                  Paused
                </div>
              ) : null}
            </main>
            <aside className="hidden min-h-0 border-l md:block">
              <Inspector car={selected} paused={snap.paused} />
            </aside>
          </div>
          <footer className="border-t">
            <Fleet cars={snap.cars} selectedId={selectedId} onSelect={setSelectedId} />
          </footer>
          <Sheet open={surpriseOpen} onOpenChange={setSurpriseOpen}>
            <SheetContent side="left" className="w-[min(100%,22rem)] p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Surprises</SheetTitle>
              </SheetHeader>
              <SurprisePanel snap={snap} selectedId={selectedId} send={send} />
            </SheetContent>
          </Sheet>
          <Sheet open={inspectOpen} onOpenChange={setInspectOpen}>
            <SheetContent side="right" className="w-[min(100%,24rem)] p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Inspector</SheetTitle>
              </SheetHeader>
              <Inspector car={selected} paused={snap.paused} />
            </SheetContent>
          </Sheet>
        </>
      ) : null}
    </div>
  );
}

function Status({ status, onRetry }: { status: string; onRetry: () => void }) {
  if (status === "open") {
    return <span className="text-xs text-muted-foreground">Socket live</span>;
  }
  if (status === "connecting") {
    return <span className="text-xs text-muted-foreground">Connecting</span>;
  }
  return (
    <Button size="xs" variant="destructive" onClick={onRetry}>
      Socket down · Retry
    </Button>
  );
}
