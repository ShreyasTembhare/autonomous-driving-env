"use client";

import { useEffect, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { Popover } from "@astryxdesign/core/Popover";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { NetworkMap, RoutePreview, TripMode } from "@/lib/types";

const STYLES = [
  { id: "cautious", label: "Cautious" },
  { id: "careful", label: "Careful" },
  { id: "impatient", label: "Impatient" },
  { id: "hurried", label: "Hurried" },
] as const;

type Place = { kind: "stub" | "pt"; value: string; label: string };

type Props = {
  mode: TripMode;
  network: NetworkMap | null;
  selectedId: string | null;
  canSpawn: boolean;
  previewRoute: (start: string, dest: string, style?: string) => Promise<RoutePreview>;
  pendingPoint: { x: number; y: number } | null;
  onMode: (mode: TripMode) => void;
  onPreview: (points: [number, number][] | null) => void;
  onSend: (message: Record<string, unknown>) => void;
  onClearPoint: () => void;
};

function placeFromPoint(point: { x: number; y: number }): Place {
  return {
    kind: "pt",
    value: `pt:${point.x.toFixed(1)},${point.y.toFixed(1)}`,
    label: `Map (${point.x.toFixed(0)}, ${point.y.toFixed(0)})`,
  };
}

function coordFromPlace(place: Place): string | { x: number; y: number } {
  if (place.kind === "stub") return place.value;
  const [x, y] = place.value.slice(3).split(",").map(Number);
  return { x, y };
}

export function TripTool({
  mode,
  network,
  selectedId,
  canSpawn,
  previewRoute,
  pendingPoint,
  onMode,
  onPreview,
  onSend,
  onClearPoint,
}: Props) {
  const [open, setOpen] = useState(false);
  const [start, setStart] = useState<Place | null>(null);
  const [dest, setDest] = useState<Place | null>(null);
  const [style, setStyle] = useState("careful");
  const [preview, setPreview] = useState<RoutePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const picking = mode !== "idle";
  const isOpen = open || picking;
  const step =
    mode === "idle"
      ? "idle"
      : mode === "reroute"
        ? dest
          ? "confirm"
          : "dest"
        : !start
          ? "start"
          : !dest
            ? "dest"
            : "confirm";

  useEffect(() => {
    if (!pendingPoint || mode === "idle") return;
    const place = placeFromPoint(pendingPoint);
    if (mode === "new" && !start) setStart(place);
    else setDest(place);
    onClearPoint();
  }, [pendingPoint, mode, start, onClearPoint]);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (mode === "idle") {
        setPreview(null);
        onPreview(null);
        return;
      }
      if (mode === "new" && (!start || !dest)) {
        setPreview(null);
        onPreview(null);
        return;
      }
      if (mode === "reroute") {
        setPreview({ ok: true, description: `Re-route to ${dest?.label ?? "…"}`, points: [] });
        onPreview(null);
        return;
      }
      setBusy(true);
      try {
        const res = await previewRoute(start!.value, dest!.value, style);
        if (cancelled) return;
        setPreview(res);
        onPreview(res.ok && res.points ? res.points : null);
      } catch {
        if (!cancelled) setPreview({ ok: false, error: "Could not reach the route service." });
      } finally {
        if (!cancelled) setBusy(false);
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [mode, start, dest, style, previewRoute, onPreview]);

  const reset = () => {
    onMode("idle");
    onPreview(null);
    setStart(null);
    setDest(null);
    setPreview(null);
    setOpen(false);
  };

  const begin = (next: TripMode) => {
    setStart(null);
    setDest(null);
    setPreview(null);
    onMode(next);
  };

  const hint =
    step === "idle"
      ? "Start a trip or send the selected car somewhere else."
      : step === "start"
        ? "Pick a street end below, or click the map, for the start."
        : step === "dest"
          ? "Pick a street end below, or click the map, for the destination."
          : busy
            ? "Planning…"
            : preview?.ok
              ? `${preview.description ?? "Route"} · ${preview.length?.toFixed(0) ?? "?"} m · ~${preview.eta?.toFixed(0) ?? "?"} s`
              : (preview?.error ?? "Confirm to send.");

  return (
    <Popover
      label="Trip"
      isOpen={isOpen}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
      isModal={false}
      hasLightDismiss={!picking}
      width={280}
      padding={3}
      content={
        <VStack gap={3}>
          {mode === "idle" ? (
            <>
              <Text color="secondary">{hint}</Text>
              <HStack gap={2}>
                <Button
                  label="New trip"
                  size="sm"
                  variant="primary"
                  isDisabled={!canSpawn}
                  tooltip={canSpawn ? undefined : "Town is full"}
                  onClick={() => begin("new")}
                />
                <Button
                  label="Re-route"
                  size="sm"
                  isDisabled={!selectedId}
                  onClick={() => begin("reroute")}
                />
              </HStack>
            </>
          ) : (
            <>
              <HStack gap={2} hAlign="between" vAlign="center">
                <Text weight="medium">{mode === "new" ? "New trip" : "Re-route selected"}</Text>
                <Button label="Cancel" size="sm" variant="ghost" onClick={reset} />
              </HStack>
              <Text color="secondary">{hint}</Text>
              {network && (step === "start" || step === "dest") ? (
                <List density="compact" edge="flush">
                  {network.stubs.map((stub) => (
                    <ListItem
                      key={stub.id}
                      label={stub.name}
                      onClick={() => {
                        const place: Place = { kind: "stub", value: stub.id, label: stub.name };
                        if (step === "start") setStart(place);
                        else setDest(place);
                      }}
                    />
                  ))}
                </List>
              ) : null}
              {mode === "new" && step === "confirm" ? (
                <SegmentedControl label="Driving style" size="sm" value={style} onChange={setStyle}>
                  {STYLES.map((item) => (
                    <SegmentedControlItem key={item.id} value={item.id} label={item.label} />
                  ))}
                </SegmentedControl>
              ) : null}
              {start || dest ? (
                <Text color="secondary">
                  {mode === "new"
                    ? `${start?.label ?? "…"} → ${dest?.label ?? "…"}`
                    : `→ ${dest?.label ?? "…"}`}
                </Text>
              ) : null}
              {step === "confirm" ? (
                <Button
                  label="Confirm"
                  variant="primary"
                  size="sm"
                  isDisabled={mode === "new" ? !preview?.ok : !dest}
                  onClick={() => {
                    if (mode === "new" && start && dest) {
                      onSend({
                        op: "spawn_trip",
                        start: coordFromPlace(start),
                        dest: coordFromPlace(dest),
                        style,
                      });
                    } else if (mode === "reroute" && selectedId && dest) {
                      onSend({
                        op: "set_destination",
                        car: selectedId,
                        dest: coordFromPlace(dest),
                      });
                    }
                    reset();
                  }}
                />
              ) : null}
            </>
          )}
        </VStack>
      }
    >
      <Button label="Trip" size="sm" variant="ghost" />
    </Popover>
  );
}
