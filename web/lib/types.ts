export type MetaAction =
  | "LANE_LEFT"
  | "IDLE"
  | "LANE_RIGHT"
  | "FASTER"
  | "SLOWER"
  | "STALLED"
  | "CRASHED";

export type SeenActor = {
  kind: "car" | "pedestrian" | "signal";
  id: string;
  name: string;
  distance: number;
  rel_speed: number;
  color?: string;
};

export type OptionRow = {
  action: string;
  label: string;
  available: boolean;
  reason: string | null;
  score: number | null;
  chosen: boolean;
  wanted: boolean;
};

export type ModelGroup = {
  name: string;
  blocks: { title: string; rows: { label: string; text: string; net: number }[] }[];
};

export type DecisionFrame = {
  sentence: string;
  brain: string;
  brain_label: string;
  checkpoint: string | null;
  uses_network: boolean;
  meta_action: MetaAction | string;
  wanted: string;
  seen: SeenActor[];
  hidden_count: number;
  constraints: string[];
  options: OptionRow[];
  filter: { wanted: string; chose: string; reason: string } | null;
  accel: number;
  steering_deg: number;
  target_speed: number;
  limits: { accel_min: number; accel_max: number; steer_deg: number; wet: boolean };
  model: {
    loaded: boolean;
    mix?: string;
    seed?: number | null;
    checkpoint?: string | null;
    text: string;
    groups?: ModelGroup[];
    probs?: { action: string; label: string; p: number }[];
    value?: number;
  };
  cone: { range: number; half_angle: number };
  history: { t: number; speed: number; action: string }[];
};

export type CarSnap = {
  id: string;
  name: string;
  color: string;
  x: number;
  y: number;
  heading: number;
  speed: number;
  length: number;
  width: number;
  stalled: boolean;
  crashed: boolean;
  axis: string;
  lane: number;
  decision: DecisionFrame;
};

export type PedSnap = {
  id: string;
  kind: "walker" | "jaywalker";
  name: string;
  x: number;
  y: number;
  heading: number;
  hit: boolean;
  path: [number, number][];
};

export type TrainState = {
  running: boolean;
  mix: string | null;
  step: number;
  budget: number;
  reward: number | null;
  crash_rate: number | null;
  ready: boolean;
  checkpoint: string | null;
  error: string | null;
};

export type Snapshot = {
  tick: number;
  time: number;
  paused: boolean;
  speed: number;
  seed: number;
  wet: boolean;
  limits: { accel: number; brake: number };
  signal: {
    phase: string;
    label: string;
    remaining: number;
    approaches: Record<"north" | "south" | "east" | "west", string>;
    lamps: { axis: string; x: number; y: number; color: string }[];
  };
  map: { stop: number; edge: number; box: number; crosswalk?: number };
  cars: CarSnap[];
  pedestrians: PedSnap[];
  log: { index: number; tick: number; time: number; label: string }[];
  all_crashed: boolean;
  train: TrainState;
};

export type SocketStatus = "connecting" | "open" | "error";
