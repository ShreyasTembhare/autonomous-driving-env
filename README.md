# The crossing

One signalized intersection, six cars, and a click-a-car inspector that shows the decision frame each car just computed. Surprises (flip the light, all-red, a jaywalker, a stall, a cut-in, wet pavement) change the running world. They do not reset it.

The Python sim is the source of truth. The page only draws snapshots and sends commands.

## Run it

From this directory, in two terminals:

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn sim.server:app --host 0.0.0.0 --port 43124
```

```bash
cd web
npm install
npm run dev
```

- Web: http://127.0.0.1:43123
- API: http://127.0.0.1:43124 (`GET /health`, websocket `/ws`)

Play and pause with the button or the space bar. Left and right arrows cycle the selected car.

## What is driving

| Car | Brain |
| --- | --- |
| Ada | Cautious rules (no network) |
| Rex | Impatient rules (no network) |
| Mina, Theo | Careful PPO, seeds 0 and 1 |
| Jules, Nova | Hurried PPO, seeds 0 and 1 |

Checkpoints in `sim/checkpoints/` are Stable-Baselines3 PPO, `MlpPolicy`, two hidden layers of 64. The town loads them on first start. A clone without the zips rebuilds them from the `.b64` text on first load. Retrain the checked-in set with:

```bash
python3 -m sim.train --steps 8192
```

The Train view in the app starts a shorter run, plots episode reward and crash rate, and hot-swaps the new weights onto the cars of that mix.

## Tests

```bash
python3 -m pytest
```

## Elsewhere in this repo

`docs/av-sim-landscape.md` is a survey of how other driving simulators expose scenes, actors, and policies. This app copies a few of those mechanisms. It does not vendor Waymo, SUMO, or CARLA.
