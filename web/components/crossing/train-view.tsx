"use client";

import { useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { ProgressBar } from "@astryxdesign/core/ProgressBar";
import {
  SegmentedControl,
  SegmentedControlItem,
} from "@astryxdesign/core/SegmentedControl";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import type { TrainState } from "@/lib/types";

export function TrainView({
  train,
  send,
}: {
  train: TrainState;
  send: (message: Record<string, unknown>) => void;
}) {
  const [mix, setMix] = useState<"careful" | "hurried">(train.mix === "hurried" ? "hurried" : "careful");
  const [steps, setSteps] = useState("4096");
  const budget = Number(steps) || 4096;
  const progress = train.budget > 0 ? Math.min(100, Math.round((train.step / train.budget) * 100)) : 0;

  return (
    <VStack gap={6} padding={8} maxWidth={640} hAlign="stretch">
      <VStack gap={2}>
        <Heading level={1}>Train a mix</Heading>
        <Text color="secondary">
          Careful penalizes crashes, red lights, and close calls with people. Hurried pays for getting through. Mina and
          Theo drive Careful. Jules and Nova drive Hurried. A finished run replaces that pair. The town keeps moving
          while this trains.
        </Text>
      </VStack>
      <SegmentedControl label="Mix" value={mix} onChange={(value) => setMix(value as "careful" | "hurried")}>
        <SegmentedControlItem value="careful" label="Careful" />
        <SegmentedControlItem value="hurried" label="Hurried" />
      </SegmentedControl>
      <HStack gap={2} vAlign="end" wrap="wrap">
        <TextInput
          label="Step budget"
          value={steps}
          inputMode="numeric"
          width={140}
          onChange={setSteps}
        />
        {[2048, 4096, 8192].map((preset) => (
          <Button key={preset} label={String(preset)} size="sm" onClick={() => setSteps(String(preset))} />
        ))}
        <Button
          label={train.running ? "Training…" : "Start PPO"}
          variant="primary"
          isDisabled={train.running}
          onClick={() => send({ op: "train", mix, steps: budget })}
        />
      </HStack>
      <List density="compact" edge="flush">
        <ListItem
          label="Steps"
          endContent={<Text hasTabularNumbers>{train.budget ? `${train.step} / ${train.budget}` : "—"}</Text>}
        />
        <ListItem
          label="Episode reward"
          endContent={<Text hasTabularNumbers>{train.reward === null ? "—" : train.reward.toFixed(2)}</Text>}
        />
        <ListItem
          label="Crash rate"
          endContent={
            <Text hasTabularNumbers>
              {train.crash_rate === null ? "—" : `${Math.round(train.crash_rate * 100)}%`}
            </Text>
          }
        />
      </List>
      <ProgressBar label="Training progress" value={progress} max={100} isLabelHidden={false} />
      {train.error ? <Text color="accent">{train.error}</Text> : null}
      {train.ready ? (
        <VStack gap={3}>
          <Heading level={2}>Weights are ready</Heading>
          <Text color="secondary">
            This {train.mix} run can go onto the learned cars of that mix. The rule cars, Ada and Rex, stay on their
            rules.
          </Text>
          <Button label="Drive these weights" variant="primary" onClick={() => send({ op: "drive_weights" })} />
        </VStack>
      ) : (
        <Text color="secondary">
          No new run yet. The cars are already on the checked-in Careful and Hurried checkpoints, two seeds each.
        </Text>
      )}
    </VStack>
  );
}
