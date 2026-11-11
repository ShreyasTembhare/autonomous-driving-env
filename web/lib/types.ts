export type MetaAction =
  | "KEEP"
  | "LEFT"
  | "RIGHT"
  | "CENTER"
  | "ABORT"
  | "STALLED"
  | "CRASHED"
  | string;

export type SeenActor = {
  kind: "car" | "pedestrian" | "signal";
  id: string;
  name: string;
  distance: number;
  rel_speed: number;
  color?: string;
};

export type CostTerm = {
  name: string;
  inputs: Record<string, unknown>;
  formula: string;
  value: number;
};

export type CandidateRow = {
  key: string;
  label: string;
  lane: number;
  feasible: boolean;
  reason: string | null;
  chosen: boolean;
  total: number;
  terms: CostTerm[];
  path: [number, number][];
  binding: string | null;
  a: number;
};

export type DecisionFrame = {
  sentence: string;
  brain: string;
  brain_label: string;
  style?: Record<string, number | string>;
  checkpoint: string | null;
  uses_network: boolean;
  meta_action: MetaAction;
  badge: string | null;
  seen: SeenActor[];
  hidden_count: number;
  accel: number;
  steering_deg: number;
  target_speed: number;
  limits: { accel_min: number; accel_max: number; steer_deg: number; wet: boolean };
  route?: {
    from: string;
    to: string;
    links: string[];
    index: number;
    maneuvers: string[];
    next: string | null;
    next_text: string | null;
    next_node: string | null;
    remaining: number;
    length: number;
    progress: number;
    need_lane: number | null;
    lane: number;
    lane_change_left: number | null;
    to_line: number | null;
    points: [number, number][];
  };
  idm?: {
    leader: { kind: string; id: string | null; name: string; reason: string; gap: number } | null;
    v: number;
    v0: number;
    v0_style: number;
    s: number | null;
    dv: number | null;
    s_star: number | null;
    a: number;
    free_a: number | null;
    formula: string;
    constraints: {
      kind: string;
      id: string | null;
      name: string;
      reason: string;
      gap: number;
      lead_v: number;
      a: number | null;
      s_star: number | null;
      formula: string;
    }[];
    T: number;
    s0: number;
    a_max: number;
    b: number;
  } | null;
  signal?: {
    node: string;
    node_name: string;
    color: string;
    remaining: number | null;
    dist: number;
    speed: number;
    t_clear: number;
    t_clear_formula: string;
    stop_comfy: number;
    stop_hard: number;
    stop_formula: string;
    req_decel: number | null;
    req_formula: string;
    hard: number;
    verdict: string;
    text: string;
  } | null;
  candidates?: CandidateRow[];
  mobil?: Record<string, unknown>[];
  shield?: {
    acted: boolean;
    a_in: number;
    a_out: number;
    comfortable: number;
    hard: number;
    text: string;
    checks: { name: string; have: number; need: number; formula: string }[];
  } | null;
  conflicts?: {
    with: string;
    name: string;
    reason: string;
    d_point: number;
    eta_self: number | null;
    eta_other: number | null;
    gap_accept: number | null;
    verdict: string;
    rule: string;
  }[];
  compare?: {
    runner: string;
    runner_key: string;
    margin: number;
    terms: { name: string; chosen: number; other: number; diff: number }[];
  } | null;
  stop_point?: { x: number; y: number; kind: string } | null;
  trip?: {
    user: boolean;
    elapsed: number;
    stops: number;
    overtakes: number;
    replans: { t: number; reason: string; route: string }[];
    arrived: boolean;
  };
  model: {
    loaded: boolean;
    mix?: string;
    seed?: number | null;
    checkpoint?: string | null;
    text: string;
    probs?: { action: string; label: string; p: number }[];
    value?: number;
  };
  history: { t: number; speed: number; action: string; badge?: string | null }[];
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
  arrived?: boolean;
  user?: boolean;
  named?: boolean;
  brain?: string;
  lane: number;
  target_lane?: number;
  leg?: string;
  link?: string | null;
  connector?: string | null;
  indicator?: string | null;
  badge?: string | null;
  from?: string;
  to?: string;
  dest?: [number, number] | null;
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
  moving?: boolean;
  path: [number, number][];
};

export type SignalNode = {
  node: string;
  name: string;
  phase: string;
  label: string;
  remaining: number | null;
  lamps: { link: string; axis: string; x: number; y: number; color: string }[];
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

export type Notice = {
  id: number;
  tick: number;
  kind: string;
  text: string;
  car: string | null;
};

export type Snapshot = {
  tick: number;
  time: number;
  paused: boolean;
  speed: number;
  seed: number;
  wet: boolean;
  limits: { accel: number; brake: number; max_speed?: number };
  signals: SignalNode[];
  cars: CarSnap[];
  pedestrians: PedSnap[];
  log: { index: number; tick: number; time: number; label: string }[];
  notices?: Notice[];
  stats?: { arrivals: number; crashes: number; ped_hits: number; trips_done: number };
  fleet?: { size: number; total: number; user: number; max: number; min: number };
  last_spawned?: string | null;
  all_crashed: boolean;
  train: TrainState;
};

export type NetworkMap = {
  bounds: { min: [number, number]; max: [number, number] };
  road_half: number;
  lane_w: number;
  box: number;
  roads: { a: [number, number]; b: [number, number]; name?: string }[];
  blocks?: { a: [number, number]; b: [number, number] }[];
  intersections: { id: string; name: string; x: number; y: number }[];
  stubs: { id: string; name: string; x: number; y: number; entry: string; exit: string }[];
  links: {
    id: string;
    from: string;
    to: string;
    axis: string;
    a: [number, number];
    b: [number, number];
  }[];
  stop_lines: { link: string; a: [number, number]; b: [number, number] }[];
  lamps: { link: string; node: string; axis: string; pos: [number, number] }[];
  crosswalks: { id: string; node: string; arm: string; a: [number, number]; b: [number, number] }[];
};

export type RoutePreview = {
  ok: boolean;
  error?: string;
  start?: { link: string; s: number; label: string };
  dest?: { link: string; s: number; label: string };
  links?: string[];
  length?: number;
  eta?: number;
  description?: string;
  points?: [number, number][];
};

export type SocketStatus = "connecting" | "open" | "error";

export type TripMode = "idle" | "new" | "reroute";
