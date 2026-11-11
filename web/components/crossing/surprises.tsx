"use client";

import { DropdownMenu } from "@astryxdesign/core/DropdownMenu";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { Snapshot } from "@/lib/types";

type Props = {
  snap: Snapshot;
  selectedId: string | null;
  selectedNode: string | null;
  send: (message: Record<string, unknown>) => void;
};

export function SceneMenu({ snap, selectedId, selectedNode, send }: Props) {
  const node = selectedNode;
  const signal = snap.signals.find((s) => s.node === node) ?? snap.signals[0];
  const hasSignal = Boolean(node);
  const hasCar = Boolean(selectedId);
  const log = snap.log.slice(-8).reverse();

  return (
    <DropdownMenu
      button={{ label: "Surprise", size: "sm", variant: "ghost" }}
      menuWidth={300}
      menuMaxHeight={480}
      header={<Text color="secondary">Changes the town that is already running.</Text>}
      footer={
        <VStack gap={2} paddingBlock={2}>
          <Text color="secondary">Log</Text>
          {log.length === 0 ? (
            <Text color="secondary">Nothing yet.</Text>
          ) : (
            <List density="compact" edge="flush">
              {log.map((row) => (
                <ListItem
                  key={`${row.index}-${row.tick}`}
                  label={row.label}
                  endContent={<Text color="secondary">Replay</Text>}
                  onClick={() => send({ op: "replay", index: row.index })}
                />
              ))}
            </List>
          )}
        </VStack>
      }
      items={[
        {
          type: "section",
          title: signal ? `${signal.name} · ${signal.label}` : "Signal",
          items: [
            {
              label: "Flip",
              description: hasSignal ? "Swap the green at this light" : "Click a signal on the map first",
              isDisabled: !hasSignal,
              onClick: () => send({ op: "flip", node }),
            },
            {
              label: "All-red",
              description: hasSignal ? "Hold every lamp red here" : "Click a signal on the map first",
              isDisabled: !hasSignal,
              onClick: () => send({ op: "all_red", node }),
            },
            {
              label: "Restore",
              description: hasSignal ? "Put this light back" : "Click a signal on the map first",
              isDisabled: !hasSignal,
              onClick: () => send({ op: "restore", node }),
            },
            { label: "Flip all", description: "Swap the green at every light", onClick: () => send({ op: "flip" }) },
          ],
        },
        { type: "divider" },
        {
          type: "section",
          title: "Street",
          items: [
            { label: "Jaywalk", description: "A person steps into the road", onClick: () => send({ op: "jaywalk", car: selectedId }) },
            {
              label: "Stall",
              description: hasCar ? "Stop the selected car" : "Select a car first",
              isDisabled: !hasCar,
              onClick: () => send({ op: "stall", car: selectedId }),
            },
            {
              label: "Cut-in",
              description: hasCar ? "A car pulls in ahead of the selected one" : "Select a car first",
              isDisabled: !hasCar,
              onClick: () => send({ op: "cut_in", car: selectedId }),
            },
            {
              label: snap.wet ? "Dry pavement" : "Wet pavement",
              description: snap.wet ? "Back to a dry road" : "Lower grip for every car",
              onClick: () => send({ op: "wet", on: !snap.wet }),
            },
          ],
        },
      ]}
    />
  );
}
