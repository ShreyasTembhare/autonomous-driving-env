# Open-source landscape for a 2D driving world

Checked 16 October 2026. Repository facts (license, archive flag, last push, star count) come from the public GitHub API unless noted. Intervention notes come from each project's README or docs.

## The vision this survey is measuring

A virtual 2D world where many autonomous vehicles learn to drive. After training, a person can change that world while the cars are moving — a traffic light flips at the wrong time, a pedestrian steps into the road, something similarly unexpected — and watch how the cars behave.

A project is close when it is actually cloneable and already has most of that shape: a 2D world, training of driving policies for more than one vehicle, and a way for a person to perturb a running scene. Traffic-only simulators stay in the survey when they are the place those perturbations already exist.

## Closest projects

| Project | World | What it trains | Live intervention | License | Last push |
| --- | --- | --- | --- | --- | --- |
| [highway-env](https://github.com/Farama-Foundation/HighwayEnv) | 2D | Driving policies | Config at reset only | MIT | 2026-10-10 |
| [GPUDrive](https://github.com/Emerge-Lab/gpudrive) | 2D | Many driving policies | Choose which logged agents are controlled | MIT | 2025-12-01 |
| [SMARTS](https://github.com/huawei-noah/SMARTS) | 2D road sim | Multi-agent driving policies | Scenario files before the run | MIT | 2025-01-31 |
| [SUMO](https://github.com/eclipse-sumo/sumo) | 2D | Traffic, not policies | GUI and TraCI while the sim runs | EPL-2.0 | 2026-10-15 |
| [Waymax](https://github.com/waymo-research/waymax) | 2D | Driving and sim-agent policies | Code edits actions inside a logged scene | Non-commercial custom | 2025-10-23 |
| [MetaDrive](https://github.com/metadriverse/metadrive) | 3D, top-down view available | Driving policies, including multi-agent | Config: density, accidents, respawn | Apache-2.0 | 2026-10-16 |
| [CARLA](https://github.com/carla-simulator/carla) | 3D | Driving policies | Python API can change lights and spawn walkers mid-run | MIT | 2026-10-15 |

Waymo Open Motion scenes, used by GPUDrive, Waymax, and Nocturne, sit under Waymo's own dataset terms. The simulator license and the data license are separate.

## Entries

### highway-env

A Gymnasium collection of tactical driving tasks: highway, merge, intersection, roundabout, parking, racetrack, and others, including multi-agent variants.

- Repo: https://github.com/Farama-Foundation/HighwayEnv
- World: 2D kinematic scene, rendered with pygame.
- Role: trains driving policies. Stable-Baselines3 examples are in the docs. About 3,300 stars.
- Live intervention: vehicle counts and behaviors are configuration, applied when an episode is built. The intersection is an unsignalized yield. The maintainer has said signal control is outside the current feature set ([issue 506](https://github.com/Farama-Foundation/HighwayEnv/issues/506)). There are no pedestrians and no control for surprising a running scene.
- License: MIT.
- Closeness: the closest small 2D world whose job is training cars. The "mess with the world" half is absent.

### GPUDrive

A data-driven multi-agent driving simulator aimed at about a million frames per second, with Gymnasium wrappers and PPO implementations (Stable-Baselines3, CleanRL / PufferLib).

- Repo: https://github.com/Emerge-Lab/gpudrive
- World: 2D bird's-eye boxes. Scenes from the Waymo Open Motion Dataset include vehicles, cyclists, and pedestrians. About 620 stars. Last push 1 December 2025.
- Role: trains driving policies for many agents at once.
- Live intervention: the user picks which agents a policy controls and which follow the log. Scenes are fixed dataset snippets. There is no console for flipping a light or inserting a new jaywalker into a running town.
- License: MIT (code). Dataset terms are separate.
- Closeness: the strongest modern 2D fleet trainer, and people are already in the scenes. It is a log player with learned controllers, which is a different product from an authored world a person edits live.

### SMARTS

Scalable Multi-Agent RL Training School: ego policies, a zoo of social agents, and background traffic on SUMO or SMARTS's own engine.

- Repo: https://github.com/huawei-noah/SMARTS
- World: 2D road-level simulation with the Envision visualizer. Maps can be SUMO, OpenDRIVE, or Waymo. About 1,100 stars. Last push 31 January 2025, with a large open-issue backlog.
- Role: trains multi-agent driving policies. Other cars can be SUMO traffic, replayed data, or frozen policies.
- Live intervention: [Scenario Studio](https://smarts.readthedocs.io/en/latest/sim/scenario_studio.html) authors traffic, social agents, and pedestrian traffic actors before the run. Envision watches. A person does not get a mid-run "jaywalk" button. SUMO underneath is what actually knows about signals.
- License: MIT.
- Closeness: the closest stack that already joins multi-agent policy training with pedestrians and traffic. The perturbation surface is a scenario file, and the project is quieter than highway-env or MetaDrive.

### SUMO

Eclipse SUMO is a microscopic traffic simulator for large networks, including pedestrians, with a GUI and a large scenario toolchain.

- Repo: https://github.com/eclipse-sumo/sumo
- World: 2D network. About 4,200 stars. Pushed 15 October 2026.
- Role: traffic-only. Driving policies show up only in projects built on top (SMARTS, Flow, Driver Dojo, LimSim).
- Live intervention: this is the existing control surface to copy. TraCI can change a traffic-light phase, insert or remove vehicles and persons, and alter speeds while the simulation is running. The GUI can inspect and edit signals. It is an engineer tool, and the cars in it are traffic models.
- License: EPL-2.0.
- Closeness: the right machinery for live surprises, and the wrong product if the goal is a fleet of learned drivers.

### Waymax

A JAX simulator for closed-loop driving research on Waymo Open Motion logs. Agents are bounding boxes.

- Repo: https://github.com/waymo-research/waymax
- World: 2D. About 1,100 stars. Last push 23 October 2025.
- Role: trains and evaluates driving policies and sim agents through dm-env and Brax adapters. Also supports open-loop prediction.
- Live intervention: the caller supplies actions in code, including for several agents. There is no viewer control for lights or for spawning a person mid-run.
- License: Waymax License Agreement for Non-Commercial Use. It is not an OSI license. It bars commercial use, real-world vehicle development, and using the code to train foundation models.
- Closeness: a serious logged multi-agent sim. The license and the fixed scenes make it a poor base for this project.

### MetaDrive

A lightweight driving simulator with procedural roads, traffic, and single- and multi-agent RL environments.

- Repo: https://github.com/metadriverse/metadrive
- World: 3D via Panda3D, with a documented top-down renderer. About 1,300 stars. Pushed 16 October 2026.
- Role: trains driving policies. The procedural multi-agent setup replaces traffic cars with controllable agents that respawn.
- Live intervention: public config covers traffic density, trigger versus respawn, and a probability of static accident objects. That is episode setup. There is no user console for a mid-run light change or a jaywalker.
- License: Apache-2.0.
- Closeness: the liveliest lightweight trainer if a 3D engine is acceptable. For a 2D world plus live edits, it is a reference for multi-agent traffic, not the base.

### CARLA

The Unreal Engine city simulator used across driving research, with a Python API for actors, weather, and sensors.

- Repo: https://github.com/carla-simulator/carla
- World: 3D. About 14,500 stars. Default branch `ue58-dev`, pushed 15 October 2026.
- Role: trains driving policies. Many stacks sit on top, including [Scenario Runner](https://github.com/carla-simulator/scenario_runner) (MIT, pushed 14 October 2026) and [CarDreamer](https://github.com/ucd-dare/CarDreamer) (world-model RL, pushed 12 December 2025; GitHub license field is "Other").
- Live intervention: the Python API can set traffic-light state and spawn vehicles and walkers while the world is running. Scenario Runner plays scripted surprises. The bundled manual-control client drives the ego car.
- License: MIT.
- Closeness: the richest runtime actor API. Wrong weight and wrong dimension for this vision. Copy the idea that lights and pedestrians are runtime objects.

### BARK

A 2D semantic simulator for behavior planning, with a small ecosystem (bark-ml, MCTS planners, a CARLA bridge).

- Repo: https://github.com/bark-simulator/bark
- World: 2D. About 300 stars. Last push 6 February 2024.
- Role: benchmarks and trains driving behavior policies. Traffic is behavior models.
- Live intervention: scenarios and models are code and config.
- License: MIT.
- Closeness: the right kind of 2D behavior sandbox, and quieter than the projects above. No pedestrians, signals, or watch-and-perturb UI.

### Driver Dojo

A Gym benchmark for generalizable driving RL, built on SUMO, with birds-eye observations and an optional CARLA view.

- Repo: https://github.com/seawee1/driver-dojo
- World: 2D through SUMO, optional 3D through CARLA. About 90 stars. Last push 10 October 2023.
- Role: trains an ego driving policy against SUMO traffic. Includes a keyboard-driving script for the ego.
- Live intervention: world edits would be SUMO's, not a built-in surprise console.
- License: GitHub reports "Other". No root `LICENSE` file was present at the usual path.
- Closeness: a clear pattern (SUMO as the world, Gym as the trainer). Too stale to build on.

### LimSim

Traffic and driving simulation, later LimSim++, with CARLA co-simulation and multimodal LLM hooks.

- Repo: https://github.com/PJLab-ADG/LimSim
- World: 2D traffic view, optional CARLA. About 560 stars. Last push 23 January 2025. Some maps are not in the repo and require a separate CitySim data request.
- Role: simulates traffic and an ego driver. Policy training of a whole fleet is not the center of the project.
- Live intervention: networks and scenarios, plus co-simulation. A mid-run user surprise console is not part of the published surface.
- License: GPL-3.0.
- Closeness: a 2D traffic viewer with an ego. The license and the co-sim scope make it a weaker base than highway-env or SMARTS.

### TorchDriveEnv

A small 2D driving RL environment whose background drivers come from Inverted AI's behavioral API. The README says the underlying TorchDriveSim includes kinematic models, agent types, and traffic controls.

- Repo: https://github.com/inverted-ai/torchdriveenv
- World: 2D (OpenCV or PyTorch3D renderer). About 30 stars. Last push 8 April 2025.
- Role: trains a driving policy. The realistic NPCs are a hosted API, so a clone is not a self-contained world.
- Live intervention: traffic controls are claimed for the simulator. The published product is a benchmark, not a user-facing perturbation console.
- License: GitHub detected none.
- Closeness: right dimensionality. The missing license and the hosted NPC API rule it out as a base.

### Flow

A framework for deep RL in traffic microsimulation, historically on SUMO, aimed at mixed-autonomy flow (shockwaves, ramps, a fraction of cars under learned control).

- Repo: https://github.com/flow-project/flow
- World: 2D through SUMO. About 1,200 stars. Last push 27 July 2024.
- Role: trains some vehicles as policies inside a traffic stream.
- Live intervention: inherits TraCI. The benchmarks themselves are fixed scenarios.
- License: MIT.
- Closeness: the classic "put RL on SUMO" architecture. The task is traffic control, which is adjacent to a town of cars you then surprise.

### CityFlow

A fast city-scale traffic simulator whose reinforcement-learning agents are the traffic signals.

- Repo: https://github.com/cityflow-project/CityFlow
- World: 2D. About 1,000 stars. Last push 19 August 2025. License Apache-2.0.
- Role: traffic-signal control, not vehicle driving policies.
- Live intervention: signal plans. No pedestrian-surprise workflow for learned drivers.
- Closeness: easy to confuse with a vehicle trainer. It is a signal-control environment.

### F1TENTH Gym

A 2D gym for an F1TENTH race car.

- Repo: https://github.com/f1tenth/f1tenth_gym
- World: 2D track. About 250 stars. Pushed 4 September 2026. License MIT.
- Role: trains one race-car policy.
- Live intervention: none for traffic lights or pedestrians.
- Closeness: a clean, active 2D vehicle gym for a different task.

### Scenic

A scenario language that samples driving situations, including pedestrians, and runs them in CARLA or MetaDrive.

- Repo: https://github.com/Scenic-Foundation/Scenic (the Berkeley LearnVerify repo resolves here)
- World: not a simulator. About 390 stars. Pushed 12 October 2026. License BSD-3-Clause.
- Role: generates scenarios. Training happens in the simulator underneath.
- Live intervention: surprises are drawn before the run, as a distribution over scenes.
- Closeness: the prior art for describing rare events. Useful as a language idea, not as the world.

### nuPlan

Motional's closed-loop planning benchmark. A planner drives through recorded scenes, with log replay or reactive simulated agents.

- Repo: https://github.com/motional/nuplan-devkit
- World: map and agent state, not a 2D game city. About 1,000 stars. Last push 27 August 2025.
- Role: evaluates planners. People train on it. It is not a fleet of policies in a free-form world.
- Live intervention: pick a scenario and an agent model. No runtime control for lights or jaywalkers.
- License: GitHub reports "Other". A root `LICENSE` file was not at the usual path.
- Closeness: important planning benchmark, far from a world a person pokes.

### CommonRoad

TUM's scenario format and motion-planning toolchain. `commonroad-io` reads, writes, and draws scenarios.

- Repo: https://github.com/CommonRoad/commonroad-io
- World: 2D scenario geometry. The io repo is small (about 20 stars) because the framework is split across repos; it was pushed 6 August 2026. License BSD-3-Clause.
- Role: benchmarks motion planners on prepared scenarios, usually one ego. `CommonRoad/commonroad-rl` on GitHub returns 404. Tutorials point at `https://gitlab.lrz.de/tum-cps/commonroad-rl.git` for the Gym environment. A third-party GitHub snapshot, [sunamatya/commonroad_rl](https://github.com/sunamatya/commonroad_rl), has been untouched since April 2022.
- Live intervention: scenarios are designed offline.
- Closeness: a scenario format worth knowing. Not a multi-vehicle training world, and the RL package is not a healthy GitHub project.

### Duckietown / gym-duckietown

A camera-view simulator of one Duckiebot in a miniature city, from lane following to navigation with dynamic obstacles.

- Repo: https://github.com/duckietown/gym-duckietown
- World: 3D rendered, seen through one robot's camera. About 90 stars. Last push 12 November 2024. The older Gazebo stack [duckietown/simulator](https://github.com/duckietown/simulator) is archived (last push November 2017).
- Role: trains one robot. Other vehicles are obstacles.
- Live intervention: keyboard control drives the robot. Maps are files.
- License: GitHub reports "Other".
- Closeness: real and cloneable, and aimed at a single physical robot. Wrong scale for a fleet in a 2D world.

## Checked and set aside

These names came up in the brief or in search. They are not candidates.

- **Nocturne** ([facebookresearch/nocturne](https://github.com/facebookresearch/nocturne)) is a 2D, partially observed multi-agent driving sim on Waymo scenes, with PPO and imitation examples, under MIT. The repository is archived. Last push 18 June 2024. GPUDrive and Waymax cover the same niche in repositories that are still open.
- **TrafficSim** (Suo, Regalado, Casas, Urtasun, CVPR 2021) is a paper about a learned multi-agent traffic model. No official public source repo was found. [traffic-sim/traffic-sim](https://github.com/traffic-sim/traffic-sim) is a different project: a macroscopic LWR traffic drawer, not that paper and not a vehicle-policy trainer.
- **LG SVL** ([lgsvl/simulator](https://github.com/lgsvl/simulator)) is a 3D simulator whose developers suspended active work on 1 January 2022. Last push 4 April 2023. The code is still public. Do not build on it.
- **AirSim** ([microsoft/AirSim](https://github.com/microsoft/AirSim)) is a 3D Unreal/Unity sim for drones and cars. Microsoft has said feature work on the original project stopped and that the repo is to be archived. The successor, [Project AirSim](https://github.com/iamaisim/ProjectAirSim), is MIT and oriented toward aerial autonomy. Neither is a 2D multi-car training world.
- **VISTA** ([vista-simulator/vista](https://github.com/vista-simulator/vista)) is a data-driven sensor simulator for a vehicle. Last push 20 November 2023. GitHub license field is "Other". It is not a multi-agent world a person edits.

## Recommendation

Learn from **highway-env**, and treat it as the base to extend.

It is a small MIT Python environment, still updated this month, whose whole job is training driving policies for cars in a 2D world. A person can read it. GPUDrive is the better reference if the goal moves to data-driven fleets that already include pedestrians, with the constraint that those fleets live inside Waymo snippets. SMARTS is the better reference for multi-agent training that already has pedestrian actors and SUMO traffic, with the constraint that it is heavier and has been quiet since January 2025. SUMO is the reference for changing lights and inserting people while a simulation runs. CARLA is the reference for doing that inside a running world through an API. Scenic is the reference for describing surprises as scenarios.

None of the 2D policy environments ship the user-facing half of the vision. Building that, at a high level, means:

1. **Actors the 2D world does not have.** Traffic lights with phases, and pedestrians that can enter the road. highway-env's intersection is an unsignalized yield.
2. **A runtime control surface.** While trained policies keep stepping, a person can flip a light, send a pedestrian across, or inject a similar surprise, without resetting the episode.
3. **A watch mode.** Many trained cars stay on screen under those policies, so the perturbation is something you see rather than a row in a log.
4. **A record of the surprise.** The same light change or jaywalker can be replayed against the same policies.

SUMO's TraCI already demonstrates (2) for traffic models. CARLA's Python API demonstrates (2) for a 3D city. The work specific to this project is those controls on a small 2D world of learned cars, plus the watch mode in (3).
