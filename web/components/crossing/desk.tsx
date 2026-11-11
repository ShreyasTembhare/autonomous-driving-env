"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell } from "@astryxdesign/core/AppShell";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Center } from "@astryxdesign/core/Center";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { DropdownMenu } from "@astryxdesign/core/DropdownMenu";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { HStack } from "@astryxdesign/core/HStack";
import { Layout, LayoutContent, LayoutFooter, LayoutHeader } from "@astryxdesign/core/Layout";
import { List, ListItem } from "@astryxdesign/core/List";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { useToast } from "@astryxdesign/core/Toast";
import { TopNav, TopNavHeading } from "@astryxdesign/core/TopNav";
import { VStack } from "@astryxdesign/core/VStack";
import { CrossingCanvas } from "@/components/crossing/canvas-view";
import { TownRail } from "@/components/crossing/town-rail";
import { CarsMenu } from "@/components/crossing/fleet";
import { Inspector } from "@/components/crossing/inspector";
import { SceneMenu } from "@/components/crossing/surprises";
import { TripTool } from "@/components/crossing/trip-tool";
import { TrainView } from "@/components/crossing/train-view";
import { useSim } from "@/lib/use-sim";
import type { CarSnap, TripMode } from "@/lib/types";

const SPEEDS = [0.5, 1, 2, 4];

export function Desk() {
  const { status, snap, network, send, previewRoute, retry } = useSim();
  const showToast = useToast();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [view, setView] = useState<"town" | "train">("town");
  const [follow, setFollow] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [hoverPath, setHoverPath] = useState<string | null>(null);
  const [tripMode, setTripMode] = useState<TripMode>("idle");
  const [previewPoints, setPreviewPoints] = useState<[number, number][] | null>(null);
  const [pendingPoint, setPendingPoint] = useState<{ x: number; y: number } | null>(null);
  const [seenGuide, setSeenGuide] = useState(true);
  const [railOpen, setRailOpen] = useState(true);
  const lastCar = useRef<CarSnap | null>(null);
  const seenNotices = useRef(new Set<number>());

  const cars = snap?.cars ?? [];
  const selected = cars.find((car) => car.id === selectedId) ?? null;
  if (selected) lastCar.current = selected;
  const inspected = selected ?? lastCar.current;

  useEffect(() => {
    try {
      setSeenGuide(localStorage.getItem("crossing-guide") === "1");
    } catch {
      setSeenGuide(false);
    }
  }, []);

  useEffect(() => {
    if (snap?.last_spawned) {
      setSelectedId(snap.last_spawned);
      setFollow(true);
    }
  }, [snap?.last_spawned]);

  useEffect(() => {
    for (const notice of snap?.notices ?? []) {
      if (seenNotices.current.has(notice.id)) continue;
      seenNotices.current.add(notice.id);
      showToast({
        body: notice.text,
        type: notice.kind === "error" ? "error" : "info",
        uniqueID: String(notice.id),
      });
    }
  }, [snap?.notices, showToast]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA")) return;
      if (event.code === "Space") {
        event.preventDefault();
        if (!snap) return;
        send({ op: snap.paused ? "play" : "pause" });
      }
      if (event.key === "f" || event.key === "F") setFollow((v) => !v);
      if (event.key === "?" || event.key === "h") setHelpOpen((v) => !v);
      if (event.key === "Escape") {
        setTripMode("idle");
        setPreviewPoints(null);
        setSelectedId(null);
      }
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        const live = cars.filter((c) => !c.arrived);
        if (!live.length) return;
        const index = Math.max(0, live.findIndex((car) => car.id === selectedId));
        const next =
          event.key === "ArrowRight"
            ? live[(index + 1) % live.length]
            : live[(index - 1 + live.length) % live.length];
        setSelectedId(next.id);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cars, selectedId, send, snap]);

  const dismissGuide = () => {
    setSeenGuide(true);
    try {
      localStorage.setItem("crossing-guide", "1");
    } catch {
      /* ignore */
    }
  };

  const banner = (
    <VStack gap={2}>
      {status === "error" && snap ? (
        <Banner
          status="error"
          container="section"
          title="The sim socket dropped"
          endContent={<Button label="Retry" size="sm" onClick={retry} />}
        />
      ) : null}
      {!seenGuide && view === "town" ? (
        <Banner
          status="info"
          container="section"
          title="Click a car to read the choice it just made"
          description="Each car picks its own speed and lane. Trip adds a car. Surprise changes a light or the street, and the town keeps running. Train fits a small network onto the careful and hurried cars."
          isDismissable
          onDismiss={dismissGuide}
          endContent={<Button label="Full guide" size="sm" onClick={() => setHelpOpen(true)} />}
        />
      ) : null}
      {snap?.all_crashed ? (
        <Banner
          status="warning"
          container="section"
          title="Every car has crashed"
          endContent={<Button label="Reset the town" size="sm" onClick={() => send({ op: "reset" })} />}
        />
      ) : null}
    </VStack>
  );

  const header = snap ? (
    <TopNav
      label="Crossing"
      heading={<TopNavHeading heading="The crossing" />}
      startContent={
        <HStack gap={2} vAlign="center">
          <SegmentedControl
            label="View"
            size="sm"
            value={view}
            onChange={(value) => {
              const next = value as "town" | "train";
              setView(next);
              if (next === "train") setSelectedId(null);
            }}
          >
            <SegmentedControlItem value="town" label="Town" />
            <SegmentedControlItem value="train" label="Train" />
          </SegmentedControl>
          <Button
            label={snap.paused ? "Play" : "Pause"}
            size="sm"
            variant="primary"
            isDisabled={status !== "open"}
            onClick={() => send({ op: snap.paused ? "play" : "pause" })}
          />
          <Button label="Guide" size="sm" variant="ghost" onClick={() => setHelpOpen(true)} />
          {view === "town" && !railOpen ? (
            <Button label="District" size="sm" variant="ghost" onClick={() => setRailOpen(true)} />
          ) : null}
        </HStack>
      }
      endContent={
        <HStack gap={1} vAlign="center">
          {view === "town" ? (
            <>
              <TripTool
                mode={tripMode}
                network={network}
                selectedId={selectedId}
                canSpawn={(snap.fleet?.total ?? 0) < (snap.fleet?.max ?? 24)}
                previewRoute={previewRoute}
                pendingPoint={pendingPoint}
                onMode={setTripMode}
                onPreview={setPreviewPoints}
                onSend={send}
                onClearPoint={() => setPendingPoint(null)}
              />
              <SceneMenu snap={snap} selectedId={selectedId} selectedNode={selectedNode} send={send} />
              <CarsMenu snap={snap} selectedId={selectedId} onSelect={setSelectedId} send={send} />
            </>
          ) : null}
          <DropdownMenu
            button={{ label: `${snap.speed}×`, size: "sm", variant: "ghost" }}
            header={<Text color="secondary">How fast the town runs</Text>}
            items={SPEEDS.map((speed) => ({
              label: `${speed}×`,
              description: speed === 1 ? "Real time" : undefined,
              onClick: () => send({ op: "speed", value: speed }),
            }))}
          />
          <DropdownMenu
            button={{ label: "More", size: "sm", variant: "ghost" }}
            items={[
              { label: "Reset", description: "Start the district over", onClick: () => send({ op: "reset" }) },
              {
                label: follow ? "Stop following" : "Follow",
                description: "Keep the map on the selected car",
                onClick: () => setFollow((v) => !v),
              },
              { label: "How this works", onClick: () => setHelpOpen(true) },
            ]}
          />
          {status === "error" ? (
            <Button label="Retry" size="sm" variant="destructive" onClick={retry} />
          ) : (
            <Text color="secondary">{status === "open" ? "Connected" : "Connecting"}</Text>
          )}
        </HStack>
      }
    />
  ) : undefined;

  let content;
  if (status === "connecting" && !snap) {
    content = (
      <Center height="100%">
        <EmptyState title="Connecting to the crossing" headingLevel={1} />
      </Center>
    );
  } else if (status === "error" && !snap) {
    content = (
      <Center height="100%">
        <EmptyState
          title="The sim socket dropped"
          headingLevel={1}
          description="Start the Python server on port 43124, then retry."
          actions={<Button label="Retry" variant="primary" onClick={retry} />}
        />
      </Center>
    );
  } else if (view === "train" && snap) {
    content = <TrainView train={snap.train} send={send} />;
  } else if (snap) {
    content = (
      <HStack height="100%" width="100%" gap={0} vAlign="stretch">
        {railOpen ? (
          <TownRail
            snap={snap}
            network={network}
            selectedId={selectedId}
            selectedNode={selectedNode}
            onSelect={setSelectedId}
            onSelectNode={setSelectedNode}
            onHide={() => setRailOpen(false)}
            send={send}
          />
        ) : null}
        <VStack height="100%" className="min-w-0 flex-1">
          <CrossingCanvas
            snap={snap}
            network={network}
            selectedId={selectedId}
            hoverPathKey={hoverPath}
            follow={follow}
            previewPoints={previewPoints}
            tripPicking={tripMode !== "idle"}
            onSelect={setSelectedId}
            onSelectNode={setSelectedNode}
            onMapClick={(x, y) => setPendingPoint({ x, y })}
          />
        </VStack>
      </HStack>
    );
  } else {
    content = null;
  }

  return (
    <>
      <AppShell
        height="fill"
        contentPadding={0}
        variant="wash"
        mobileNav={false}
        banner={snap ? banner : undefined}
        topNav={header}
      >
        {content}
      </AppShell>
      <Inspector
        car={inspected}
        isOpen={Boolean(selected)}
        paused={Boolean(snap?.paused)}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
        onHoverOption={setHoverPath}
      />
      <Dialog isOpen={helpOpen} onOpenChange={setHelpOpen} width={440}>
        <Layout
          header={
            <LayoutHeader>
              <DialogHeader title="How this works" onOpenChange={setHelpOpen} />
            </LayoutHeader>
          }
          content={
            <LayoutContent>
              <VStack gap={4}>
                <Text>
                  Six streets, eight lights, and cars that pick their own speed and lane. Click a car and the side
                  panel shows the choice it just made.
                </Text>
                <VStack gap={3}>
                  <VStack gap={1}>
                    <Text weight="medium">Cars</Text>
                    <Text color="secondary">
                      Pick a name, or click one on the map. Arrow keys move through the ones still driving.
                    </Text>
                  </VStack>
                  <VStack gap={1}>
                    <Text weight="medium">Trip</Text>
                    <Text color="secondary">Add a car, or send the selected one to a new destination.</Text>
                  </VStack>
                  <VStack gap={1}>
                    <Text weight="medium">Surprise</Text>
                    <Text color="secondary">
                      Flip a light, send a jaywalker, stall a car, or wet the pavement. The town keeps running.
                    </Text>
                  </VStack>
                  <VStack gap={1}>
                    <Text weight="medium">Train</Text>
                    <Text color="secondary">
                      Fit a small network onto the careful and hurried cars. Their rules still drive.
                    </Text>
                  </VStack>
                </VStack>
                <Text color="secondary">
                  Green, yellow, and red are the signals. Click a lamp before Flip, All-red, or Restore. The line behind
                  a selected car is the route it is on.
                </Text>
                <Heading level={2}>Keys</Heading>
                <List density="compact" edge="flush">
                  <ListItem label="Play or pause" endContent={<Text color="secondary">Space</Text>} />
                  <ListItem label="Next or previous car" endContent={<Text color="secondary">← →</Text>} />
                  <ListItem label="Follow the selected car" endContent={<Text color="secondary">F</Text>} />
                  <ListItem label="Zoom to a car" description="Double-click it" />
                  <ListItem label="Cancel a trip or clear the selection" endContent={<Text color="secondary">Esc</Text>} />
                  <ListItem label="Open this again" endContent={<Text color="secondary">? or H</Text>} />
                </List>
              </VStack>
            </LayoutContent>
          }
          footer={
            <LayoutFooter>
              <Button
                label="Got it"
                variant="primary"
                onClick={() => {
                  dismissGuide();
                  setHelpOpen(false);
                }}
              />
            </LayoutFooter>
          }
        />
      </Dialog>
    </>
  );
}
