"use client";

import { ScrollArea } from "@/components/ui/scroll-area";
import type { CarSnap, DecisionFrame } from "@/lib/types";

export function Inspector({ car, paused }: { car: CarSnap | null; paused: boolean }) {
  if (!car) {
    return (
      <div className="flex h-full items-center px-5">
        <p className="text-sm leading-6 text-muted-foreground">
          Select a car to see what it sees and why it picked this move.
        </p>
      </div>
    );
  }
  const frame = car.decision;
  return (
    <ScrollArea className="h-full">
      <div className="space-y-4 p-3 pb-8">
        <header>
          <div className="flex items-center gap-2">
            <span className="size-3 rounded-full" style={{ background: car.color }} />
            <h2 className="text-base font-medium">{car.name}</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {frame.brain_label}
            {frame.checkpoint ? ` · ${frame.checkpoint}` : ""} · {car.speed.toFixed(1)} m/s ·{" "}
            {Math.round(car.speed * 3.6)} km/h · {actionLabel(frame.meta_action)}
          </p>
          {paused ? (
            <p className="mt-1 text-xs text-muted-foreground">The frame is frozen while the town is paused.</p>
          ) : null}
        </header>
        <p className="text-sm leading-6">{frame.sentence}</p>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">Seen</h3>
          {frame.seen.length === 0 ? (
            <p className="text-xs text-muted-foreground">Nothing in the cone.</p>
          ) : (
            <ul className="space-y-1">
              {frame.seen.map((row) => (
                <li key={row.id} className="flex items-baseline justify-between gap-2 text-xs">
                  <span>
                    <span className="text-muted-foreground capitalize">{row.kind}</span> · {row.name}
                    {row.color ? ` · ${row.color}` : ""}
                  </span>
                  <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                    {row.distance.toFixed(0)} m · {rateText(row.rel_speed)}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {frame.hidden_count} outside the cone
          </p>
        </section>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">
            Constraints
          </h3>
          {frame.constraints.length === 0 ? (
            <p className="text-xs text-muted-foreground">None fired.</p>
          ) : (
            <ul className="space-y-1 text-xs">
              {frame.constraints.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
        </section>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">Options</h3>
          <OptionList frame={frame} color={car.color} />
        </section>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">Controls</h3>
          <p className="font-mono text-xs leading-5">
            accel {frame.accel.toFixed(1)} m/s² · steer {frame.steering_deg.toFixed(1)}° · target{" "}
            {frame.target_speed.toFixed(1)} m/s
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {frame.limits.wet ? "Wet pavement" : "Dry pavement"} · accel {frame.limits.accel_min} to{" "}
            {frame.limits.accel_max} m/s² · steer ±{frame.limits.steer_deg}°
          </p>
        </section>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">
            Learned model
          </h3>
          <p className="text-xs leading-5">{frame.model.text}</p>
          {frame.model.loaded && frame.model.groups ? (
            <div className="mt-2 space-y-2">
              {frame.model.groups.map((group) => (
                <div key={group.name}>
                  <div className="text-xs font-medium">{group.name}</div>
                  {group.blocks.map((block) => (
                    <div key={`${group.name}-${block.title}`} className="mt-1">
                      <div className="text-[11px] text-muted-foreground">{block.title}</div>
                      {block.rows.map((row) => (
                        <div
                          key={`${block.title}-${row.label}`}
                          className="flex justify-between gap-2 font-mono text-[11px]"
                        >
                          <span>
                            {row.label} <span className="text-muted-foreground">{row.text}</span>
                          </span>
                          <span className="text-muted-foreground">{row.net.toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              ))}
              {frame.model.probs ? (
                <div>
                  <div className="mb-1 text-xs font-medium">Action probabilities</div>
                  {frame.model.probs.map((row) => (
                    <div key={row.action} className="mb-1">
                      <div className="flex justify-between text-[11px]">
                        <span>{row.label}</span>
                        <span className="font-mono">{Math.round(row.p * 100)}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full bg-primary" style={{ width: `${Math.round(row.p * 100)}%` }} />
                      </div>
                    </div>
                  ))}
                  <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                    value {frame.model.value?.toFixed(2)}
                  </p>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
        <section>
          <h3 className="mb-1.5 text-[11px] tracking-wide text-muted-foreground uppercase">
            Last few seconds
          </h3>
          <History frame={frame} />
        </section>
      </div>
    </ScrollArea>
  );
}

function OptionList({ frame, color }: { frame: DecisionFrame; color: string }) {
  const scores = frame.options
    .map((row) => row.score)
    .filter((score): score is number => score !== null);
  const min = scores.length ? Math.min(...scores, 0) : 0;
  const max = scores.length ? Math.max(...scores, 0) : 1;
  const span = max - min || 1;
  return (
    <ul className="space-y-1.5">
      {frame.options.map((row) => {
        const width = row.score === null ? 0 : ((row.score - min) / span) * 100;
        return (
          <li
            key={row.action}
            className="rounded-md border px-2 py-1.5"
            style={row.chosen ? { borderColor: color } : undefined}
          >
            <div className="flex items-center justify-between gap-2 text-xs">
              <span>{row.label}</span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {row.score === null ? "—" : row.score.toFixed(2)}
                {row.chosen ? " · chosen" : ""}
                {row.wanted && !row.chosen ? " · wanted" : ""}
              </span>
            </div>
            {row.available ? (
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full" style={{ width: `${width}%`, background: color }} />
              </div>
            ) : (
              <p className="mt-0.5 text-[11px] text-muted-foreground">{row.reason}</p>
            )}
          </li>
        );
      })}
      {frame.filter ? (
        <li className="text-xs leading-5 text-muted-foreground">
          wanted {frame.filter.wanted}, filter chose {frame.filter.chose}, {frame.filter.reason}.
        </li>
      ) : null}
    </ul>
  );
}

function History({ frame }: { frame: DecisionFrame }) {
  const points = frame.history;
  if (points.length < 2) {
    return <p className="text-xs text-muted-foreground">Speed history fills in as the car drives.</p>;
  }
  const speeds = points.map((point) => point.speed);
  const min = Math.min(...speeds);
  const max = Math.max(...speeds, min + 0.5);
  const w = 280;
  const h = 48;
  const path = points
    .map((point, index) => {
      const x = (index / (points.length - 1)) * w;
      const y = h - ((point.speed - min) / (max - min)) * (h - 4) - 2;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const changes = points.filter((point, index) => index === 0 || point.action !== points[index - 1].action);
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} className="h-12 w-full">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
      <p className="font-mono text-[11px] text-muted-foreground">
        {min.toFixed(1)}–{max.toFixed(1)} m/s
      </p>
      <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
        {changes
          .slice(-6)
          .map((point) => `${point.t.toFixed(1)}s ${actionLabel(point.action)}`)
          .join(" · ")}
      </p>
    </div>
  );
}

function actionLabel(action: string) {
  const labels: Record<string, string> = {
    LANE_LEFT: "Lane left",
    IDLE: "Hold",
    LANE_RIGHT: "Lane right",
    FASTER: "Faster",
    SLOWER: "Slower",
    STALLED: "Stalled",
    CRASHED: "Crashed",
  };
  return labels[action] ?? action;
}

function rateText(rate: number) {
  if (rate < -0.2) return `closing ${Math.abs(rate).toFixed(1)} m/s`;
  if (rate > 0.2) return `opening ${rate.toFixed(1)} m/s`;
  return "matched";
}
