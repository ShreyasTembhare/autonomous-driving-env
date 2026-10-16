"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { TrainState } from "@/lib/types";

export function TrainView({
  train,
  send,
}: {
  train: TrainState;
  send: (message: Record<string, unknown>) => void;
}) {
  const [mix, setMix] = useState<"careful" | "hurried">(
    train.mix === "hurried" ? "hurried" : "careful",
  );
  const [steps, setSteps] = useState(4096);
  const progress = train.budget > 0 ? Math.min(100, Math.round((train.step / train.budget) * 100)) : 0;

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-medium">Train a mix</h2>
        <p className="mt-1 max-w-xl text-sm leading-6 text-muted-foreground">
          Careful penalizes crashes, red lights, and close calls with people. Hurried pays for
          getting through. Mina and Theo drive Careful. Jules and Nova drive Hurried. A finished
          run replaces that pair. The town keeps moving while this trains.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant={mix === "careful" ? "default" : "outline"} onClick={() => setMix("careful")}>
          Careful
        </Button>
        <Button variant={mix === "hurried" ? "default" : "outline"} onClick={() => setMix("hurried")}>
          Hurried
        </Button>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted-foreground">
          Step budget
          <Input
            className="mt-1 w-32"
            type="number"
            min={256}
            max={32768}
            value={steps}
            onChange={(event) => setSteps(Number(event.target.value) || 4096)}
          />
        </label>
        {[2048, 4096, 8192].map((preset) => (
          <Button key={preset} size="sm" variant="outline" onClick={() => setSteps(preset)}>
            {preset}
          </Button>
        ))}
        <Button disabled={train.running} onClick={() => send({ op: "train", mix, steps })}>
          {train.running ? "Training…" : "Start PPO"}
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <Stat title="Steps" value={train.budget ? `${train.step} / ${train.budget}` : "—"} />
        <Stat title="Episode reward" value={train.reward === null ? "—" : train.reward.toFixed(2)} />
        <Stat
          title="Crash rate"
          value={train.crash_rate === null ? "—" : `${Math.round(train.crash_rate * 100)}%`}
        />
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>
      {train.error ? <p className="text-sm text-destructive">{train.error}</p> : null}
      {train.ready ? (
        <Card>
          <CardHeader>
            <CardTitle>Weights are ready</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              This {train.mix} run can go onto the learned cars of that mix. The rule cars, Ada and
              Rex, stay on their rules.
            </p>
            <Button onClick={() => send({ op: "drive_weights" })}>Drive these weights</Button>
          </CardContent>
        </Card>
      ) : (
        <p className="text-sm text-muted-foreground">
          No new run yet. The cars are already on the checked-in Careful and Hurried checkpoints,
          two seeds each.
        </p>
      )}
    </div>
  );
}

function Stat({ title, value }: { title: string; value: string }) {
  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle className="text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent className="font-mono text-lg">{value}</CardContent>
    </Card>
  );
}
