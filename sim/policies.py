"""Checkpoint loading and the network's read of one observation."""

from __future__ import annotations

from pathlib import Path

from sim.geom import ACTIONS

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
_CACHE: dict[str, object] = {}


def checkpoint_file(brain: str, seed: int) -> Path:
    return CHECKPOINT_DIR / f"{brain}_seed{seed}.zip"


def load_checkpoint(path: str | Path, force: bool = False):
    key = str(path)
    if not force and key in _CACHE:
        return _CACHE[key]
    from stable_baselines3 import PPO

    model = PPO.load(key, device="cpu")
    _CACHE[key] = model
    return model


def network_preference(model, vector):
    """Return action, logits, probabilities, and value for one observation."""
    import numpy as np
    import torch

    obs = np.asarray(vector, dtype=np.float32)
    obs_tensor, _ = model.policy.obs_to_tensor(obs)
    with torch.no_grad():
        dist = model.policy.get_distribution(obs_tensor)
        logits = dist.distribution.logits.detach().cpu().numpy().reshape(-1)
        probs = dist.distribution.probs.detach().cpu().numpy().reshape(-1)
        value = float(model.policy.predict_values(obs_tensor).detach().cpu().numpy().reshape(-1)[0])
    scores = {action: float(logits[i]) for i, action in enumerate(ACTIONS)}
    prob_map = {action: float(probs[i]) for i, action in enumerate(ACTIONS)}
    action = max(ACTIONS, key=lambda name: scores[name])
    return action, scores, prob_map, value
