"""Train Careful and Hurried PPO policies. MlpPolicy, two hidden layers of 64."""

from __future__ import annotations

from pathlib import Path

from sim.policies import CHECKPOINT_DIR


def train_mix(mix: str, steps: int, seed: int, out_path: Path, progress=None) -> Path:
    from stable_baselines3 import PPO
    from stable_baselines3.common.callbacks import BaseCallback

    from sim.env import CrossingEnv

    env = CrossingEnv(mix=mix)

    class _Progress(BaseCallback):
        def __init__(self):
            super().__init__()
            self._ep_rewards: list[float] = []
            self._ep_crash: list[float] = []
            self._current = 0.0

        def _on_step(self) -> bool:
            reward = float(self.locals["rewards"][0])
            done = bool(self.locals["dones"][0])
            info = self.locals["infos"][0]
            self._current += reward
            if done:
                crashed = bool(info.get("crashed") or info.get("hit_ped"))
                self._ep_rewards.append(self._current)
                self._ep_crash.append(1.0 if crashed else 0.0)
                self._current = 0.0
            if progress and (self.n_calls % 25 == 0 or done):
                recent_r = self._ep_rewards[-8:]
                recent_c = self._ep_crash[-8:]
                progress(
                    {
                        "step": int(self.num_timesteps),
                        "reward": (sum(recent_r) / len(recent_r)) if recent_r else None,
                        "crash_rate": (sum(recent_c) / len(recent_c)) if recent_c else None,
                    }
                )
            return True

    model = PPO(
        "MlpPolicy",
        env,
        policy_kwargs={"net_arch": [64, 64]},
        learning_rate=3e-4,
        n_steps=512,
        batch_size=128,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        ent_coef=0.01,
        vf_coef=0.5,
        seed=seed,
        device="cpu",
        verbose=0,
    )
    model.learn(total_timesteps=int(steps), callback=_Progress())
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(out_path))
    env.close()
    return out_path


def train_checked_in(steps: int = 8192) -> list[Path]:
    """The four checkpoints the town loads on first start."""
    written = []
    for mix, seed in (("careful", 0), ("careful", 1), ("hurried", 0), ("hurried", 1)):
        path = CHECKPOINT_DIR / f"{mix}_seed{seed}.zip"
        print(f"training {mix} seed {seed} for {steps} steps → {path.name}", flush=True)

        def _print(update, _mix=mix, _seed=seed, _steps=steps):
            step = int(update["step"])
            if step % 1024 != 0 and step < _steps:
                return
            reward = update["reward"]
            crash = update["crash_rate"]
            reward_s = "—" if reward is None else f"{reward:.2f}"
            crash_s = "—" if crash is None else f"{crash:.0%}"
            print(
                f"  {_mix} seed {_seed}: {step}/{_steps}  reward {reward_s}  crash {crash_s}",
                flush=True,
            )

        train_mix(mix, steps, seed, path, progress=_print)
        written.append(path)
    return written


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train Careful and Hurried checkpoints")
    parser.add_argument("--steps", type=int, default=8192)
    args = parser.parse_args()
    train_checked_in(args.steps)
