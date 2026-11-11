"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { ScrollableArea } from "@astryxdesign/core/ScrollableArea";
import { Section } from "@astryxdesign/core/Section";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { NetworkMap, Snapshot } from "@/lib/types";

const CAST = [
  { name: "Ada", note: "Cautious. Wants 9 m/s and leaves a longer gap." },
  { name: "Rex", note: "Impatient. Wants 13.5 m/s and takes a shorter gap." },
  { name: "Mina", note: "Careful, seed 0. Train can fit a network onto this style." },
  { name: "Theo", note: "Careful, seed 1. Same rules as Mina." },
  { name: "Jules", note: "Hurried, seed 0. Wants 14 m/s." },
  { name: "Nova", note: "Hurried, seed 1. Same rules as Jules." },
];

function clock(seconds: number) {
  const total = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function streetLine(network: NetworkMap | null, signals: number) {
  const lights = network?.intersections.length || signals;
  return `Harbor, Market, and Ridge run east and west. Cedar, Main, and Mill run north and south. ${lights} lights time the crossings.`;
}

export function TownRail({
  snap,
  network,
  selectedId,
  selectedNode,
  onSelect,
  onSelectNode,
  onHide,
  send,
}: {
  snap: Snapshot;
  network: NetworkMap | null;
  selectedId: string | null;
  selectedNode: string | null;
  onSelect: (id: string) => void;
  onSelectNode: (node: string) => void;
  onHide: () => void;
  send: (message: Record<string, unknown>) => void;
}) {
  const live = snap.cars.filter((car) => !car.arrived);
  const named = new Set(CAST.map((person) => person.name));
  const extras = live.filter((car) => !named.has(car.name));
  const byName = new Map(live.map((car) => [car.name, car]));
  const log = snap.log.slice(-8).reverse();
  const people = snap.pedestrians.filter((ped) => !ped.hit);
  const jaywalkers = people.filter((ped) => ped.kind === "jaywalker");
  const crossing = people.length - jaywalkers.length;

  return (
    <Section width={340} height="100%" padding={0} dividers={["end"]} className="shrink-0">
      <ScrollableArea label="The district" height="100%" padding={4}>
        <VStack gap={5}>
          <HStack hAlign="between" vAlign="center">
            <Heading level={2}>The district</Heading>
            <Button label="Hide" size="sm" variant="ghost" onClick={onHide} />
          </HStack>
          <Text color="secondary">
            {streetLine(network, snap.signals.length)} Each car picks its own speed and lane. Click a name, or a car on the map, and the
            side panel shows the choice it just made.
          </Text>
          <MetadataList>
            <MetadataListItem label="Time">{clock(snap.time)}</MetadataListItem>
            <MetadataListItem label="Pavement">{snap.wet ? "Wet" : "Dry"}</MetadataListItem>
            <MetadataListItem label="Driving">{String(live.length)}</MetadataListItem>
            <MetadataListItem label="Arrivals">{String(snap.stats?.arrivals ?? 0)}</MetadataListItem>
            <MetadataListItem label="Crashes">{String(snap.stats?.crashes ?? 0)}</MetadataListItem>
            <MetadataListItem label="People hit">{String(snap.stats?.ped_hits ?? 0)}</MetadataListItem>
          </MetadataList>

          <VStack gap={2}>
            <Heading level={3}>Drivers</Heading>
            <List density="compact" edge="flush" hasDividers>
              {CAST.map((person) => {
                const car = byName.get(person.name);
                return (
                  <ListItem
                    key={person.name}
                    label={person.name}
                    description={<Text color="secondary">{person.note}</Text>}
                    isSelected={car?.id === selectedId}
                    onClick={car ? () => onSelect(car.id) : undefined}
                    endContent={
                      <Text color="secondary">
                        {car ? (car.crashed ? "Crashed" : `${car.speed.toFixed(0)} m/s`) : "Away"}
                      </Text>
                    }
                  />
                );
              })}
            </List>
          </VStack>

          <VStack gap={2}>
            <Heading level={3}>On the road</Heading>
            {extras.length === 0 ? (
              <Text color="secondary">Only the named drivers are out.</Text>
            ) : (
              <List density="compact" edge="flush" hasDividers>
                {extras.map((car) => (
                  <ListItem
                    key={car.id}
                    label={car.name}
                    description={
                      car.crashed
                        ? "Crashed"
                        : `${car.decision.brain_label} · ${car.from ?? "?"} to ${car.to ?? "?"}`
                    }
                    isSelected={car.id === selectedId}
                    onClick={() => onSelect(car.id)}
                    endContent={<Text color="secondary">{car.speed.toFixed(0)} m/s</Text>}
                  />
                ))}
              </List>
            )}
          </VStack>

          <VStack gap={2}>
            <Heading level={3}>Lights</Heading>
            <List density="compact" edge="flush" hasDividers>
              {snap.signals.map((signal) => (
                <ListItem
                  key={signal.node}
                  label={signal.name}
                  description={
                    signal.remaining == null ? signal.label : `${signal.label}, ${Math.ceil(signal.remaining)}s`
                  }
                  isSelected={signal.node === selectedNode}
                  onClick={() => onSelectNode(signal.node)}
                />
              ))}
            </List>
          </VStack>

          {people.length > 0 ? (
            <VStack gap={2}>
              <Heading level={3}>On foot</Heading>
              {crossing > 0 ? (
                <Text color="secondary">
                  {crossing} {crossing === 1 ? "person is" : "people are"} on the crosswalks.
                </Text>
              ) : null}
              {jaywalkers.length > 0 ? (
                <List density="compact" edge="flush">
                  {jaywalkers.map((ped) => (
                    <ListItem key={ped.id} label={ped.name} description="Stepped into the road" />
                  ))}
                </List>
              ) : null}
            </VStack>
          ) : null}

          <VStack gap={2}>
            <Heading level={3}>Just now</Heading>
            {log.length === 0 ? (
              <Text color="secondary">Nothing has happened yet.</Text>
            ) : (
              <List density="compact" edge="flush" hasDividers>
                {log.map((row) => (
                  <ListItem
                    key={`${row.index}-${row.tick}`}
                    label={row.label}
                    description={clock(row.time)}
                    endContent={<Text color="secondary">Replay</Text>}
                    onClick={() => send({ op: "replay", index: row.index })}
                  />
                ))}
              </List>
            )}
          </VStack>
        </VStack>
      </ScrollableArea>
    </Section>
  );
}
