"use client";

import { useState } from "react";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { Drawer, DrawerHeader } from "@astryxdesign/core/Drawer";
import { Layout, LayoutContent } from "@astryxdesign/core/Layout";
import { List, ListItem } from "@astryxdesign/core/List";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import { Tab, TabList } from "@astryxdesign/core/TabList";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { CandidateRow, CarSnap, DecisionFrame } from "@/lib/types";

type TabId = "why" | "options" | "math" | "trip";

export function Inspector({
  car,
  isOpen,
  paused,
  onOpenChange,
  onHoverOption,
}: {
  car: CarSnap | null;
  isOpen: boolean;
  paused: boolean;
  onOpenChange: (open: boolean) => void;
  onHoverOption?: (key: string | null) => void;
}) {
  const [tab, setTab] = useState<TabId>("why");
  const frame = car?.decision;
  const title = car?.name ?? "Car";

  return (
    <Drawer
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      label={title}
      width={360}
      hasScrim={false}
      padding={0}
    >
      <Layout
        header={
          <DrawerHeader
            title={title}
            subtitle={frame ? `${frame.brain_label} · ${frame.meta_action}` : undefined}
            onOpenChange={onOpenChange}
            hasDivider
          />
        }
        content={
          <LayoutContent>
            {car && frame ? (
              <VStack gap={4}>
                {paused ? <Text color="secondary">The frame is frozen while the town is paused.</Text> : null}
                <TabList value={tab} onChange={(value) => setTab(value as TabId)} size="sm" role="tablist" hasDivider>
                  <Tab value="why" label="Why" panelId="inspect-why" />
                  <Tab value="options" label="Options" panelId="inspect-options" />
                  <Tab value="math" label="Math" panelId="inspect-math" />
                  <Tab value="trip" label="Trip" panelId="inspect-trip" />
                </TabList>
                {tab === "why" ? <WhyTab car={car} frame={frame} /> : null}
                {tab === "options" ? <OptionsTab frame={frame} onHover={onHoverOption} /> : null}
                {tab === "math" ? <MathTab frame={frame} /> : null}
                {tab === "trip" ? <TripTab frame={frame} /> : null}
              </VStack>
            ) : (
              <Text color="secondary">Click a car to see why it moves.</Text>
            )}
          </LayoutContent>
        }
      />
    </Drawer>
  );
}

function WhyTab({ car, frame }: { car: CarSnap; frame: DecisionFrame }) {
  const chosen = frame.candidates?.find((c) => c.chosen);
  const facts = [
    { label: "Speed", value: `${car.speed.toFixed(1)} m/s · ${Math.round(car.speed * 3.6)} km/h` },
    car.from && car.to ? { label: "Route", value: `${car.from} → ${car.to}` } : null,
    frame.signal ? { label: "Signal", value: frame.signal.text } : null,
    frame.shield?.acted ? { label: "Shield", value: frame.shield.text } : null,
    frame.compare
      ? {
          label: "Runner-up",
          value: `${chosen?.label ?? "this"} over ${frame.compare.runner} by ${frame.compare.margin.toFixed(2)}`,
        }
      : null,
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <VStack gap={4}>
      <Text>{frame.sentence}</Text>
      <List density="compact" edge="flush">
        {facts.map((fact) => (
          <ListItem key={fact.label} label={fact.label} description={fact.value} />
        ))}
      </List>
    </VStack>
  );
}

function OptionsTab({
  frame,
  onHover,
}: {
  frame: DecisionFrame;
  onHover?: (key: string | null) => void;
}) {
  const rows = frame.candidates ?? [];
  if (!rows.length) {
    return <Text color="secondary">No candidates this tick.</Text>;
  }
  return (
    <List density="compact" edge="flush">
      {rows.map((cand: CandidateRow) => (
        <ListItem
          key={cand.key}
          label={`${cand.label}${cand.chosen ? " · chosen" : ""}${cand.feasible ? "" : " · blocked"}`}
          description={
            cand.reason ||
            cand.terms
              .slice(0, 3)
              .map((term) => `${term.name} ${term.value.toFixed(2)}`)
              .join(" · ")
          }
          endContent={<Text hasTabularNumbers>{cand.total.toFixed(2)}</Text>}
          isSelected={cand.chosen}
          onMouseEnter={() => onHover?.(cand.key)}
          onMouseLeave={() => onHover?.(null)}
        />
      ))}
    </List>
  );
}

function MathTab({ frame }: { frame: DecisionFrame }) {
  return (
    <VStack gap={2}>
      {frame.idm ? (
        <Collapsible trigger="IDM" defaultIsOpen>
          <VStack gap={2} paddingBlock={2}>
            <Text>{frame.idm.formula}</Text>
            <Text color="secondary">
              v₀ {frame.idm.v0.toFixed(1)} · T {frame.idm.T.toFixed(1)} s · s₀ {frame.idm.s0.toFixed(1)} m · a_max{" "}
              {frame.idm.a_max.toFixed(1)} · b {frame.idm.b.toFixed(1)}
            </Text>
            <Text color="secondary">
              {frame.idm.leader
                ? `Leader: ${frame.idm.leader.name} (${frame.idm.leader.kind}) · gap ${frame.idm.leader.gap.toFixed(1)} m · ${frame.idm.leader.reason}`
                : "Free road — no binding leader."}
            </Text>
          </VStack>
        </Collapsible>
      ) : null}
      {frame.signal ? (
        <Collapsible trigger="Signal" defaultIsOpen={false}>
          <VStack gap={2} paddingBlock={2}>
            <Text>{frame.signal.text}</Text>
            <Text color="secondary">{frame.signal.t_clear_formula}</Text>
            <Text color="secondary">{frame.signal.stop_formula}</Text>
            <Text color="secondary">{frame.signal.req_formula}</Text>
          </VStack>
        </Collapsible>
      ) : null}
      {(frame.mobil ?? []).map((row, i) => (
        <Collapsible key={i} trigger={`MOBIL · lane ${String(row.lane)}`} defaultIsOpen={false}>
          <VStack gap={2} paddingBlock={2}>
            <Text>{String(row.formula ?? "")}</Text>
            <Text color="secondary">
              {row.passes ? "Passes" : "Fails"} · safe={String(row.safe)} · incentive {Number(row.incentive).toFixed(2)}
            </Text>
          </VStack>
        </Collapsible>
      ))}
      {frame.shield ? (
        <Collapsible trigger="Shield" defaultIsOpen={false}>
          <VStack gap={2} paddingBlock={2}>
            <Text>{frame.shield.text}</Text>
            <Text color="secondary">
              a_in {frame.shield.a_in.toFixed(2)} → a_out {frame.shield.a_out.toFixed(2)} · comfort −{frame.shield.comfortable}{" "}
              · hard −{frame.shield.hard}
            </Text>
          </VStack>
        </Collapsible>
      ) : null}
      {(frame.conflicts ?? []).length ? (
        <Collapsible trigger="Conflicts" defaultIsOpen={false}>
          <List density="compact" edge="flush">
            {(frame.conflicts ?? []).slice(0, 6).map((c) => (
              <ListItem
                key={`${c.with}-${c.d_point}`}
                label={c.name}
                description={`${c.rule} · ${c.verdict} · d=${c.d_point.toFixed(1)} m`}
              />
            ))}
          </List>
        </Collapsible>
      ) : null}
    </VStack>
  );
}

function TripTab({ frame }: { frame: DecisionFrame }) {
  const route = frame.route;
  const trip = frame.trip;
  const progress = route && route.length > 0 ? Math.min(100, (route.progress / route.length) * 100) : 0;
  return (
    <VStack gap={4}>
      {route ? (
        <VStack gap={2}>
          <Text>
            {route.from} → {route.to} · {route.progress.toFixed(0)} / {route.length.toFixed(0)} m · {route.remaining.toFixed(0)} m
            left
          </Text>
          <ProgressBar label="Route progress" value={progress} max={100} isLabelHidden />
          <Text color="secondary">
            Next: {route.next_text ?? "arrive"}
            {route.next_node ? ` at ${route.next_node}` : ""}
          </Text>
        </VStack>
      ) : (
        <Text color="secondary">No route yet.</Text>
      )}
      {trip ? (
        <Text color="secondary">
          {trip.elapsed.toFixed(0)} s · {trip.stops} stops · {trip.overtakes} overtakes
          {trip.user ? " · user trip" : ""}
        </Text>
      ) : null}
      <Text color="secondary">{frame.model.text}</Text>
      <Collapsible trigger="Controls and actors" defaultIsOpen={false}>
        <VStack gap={3} paddingBlock={2}>
          <Text>
            accel {frame.accel.toFixed(1)} m/s² · steer {frame.steering_deg.toFixed(1)}° · target {frame.target_speed.toFixed(1)}{" "}
            m/s
          </Text>
          {frame.seen.length === 0 ? (
            <Text color="secondary">Nothing in the cone. {frame.hidden_count} outside.</Text>
          ) : (
            <List density="compact" edge="flush">
              {frame.seen.map((row) => (
                <ListItem
                  key={row.id}
                  label={`${row.kind} · ${row.name}`}
                  endContent={<Text hasTabularNumbers>{row.distance.toFixed(0)} m</Text>}
                />
              ))}
            </List>
          )}
        </VStack>
      </Collapsible>
    </VStack>
  );
}
