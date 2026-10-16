"""Checkpoint loading and the network's read of one observation."""

from __future__ import annotations

import base64
from pathlib import Path

from sim.geom import ACTIONS

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"
_CACHE: dict[str, object] = {}


def checkpoint_file(brain: str, seed: int) -> Path:
    return CHECKPOINT_DIR / f"{brain}_seed{seed}.zip"


def _checkpoint_text(path: Path) -> str:
    """ASCII base64 stored beside a missing zip, as one file or ordered pieces."""
    single = Path(str(path) + ".b64")
    if single.is_file():
        return single.read_text(encoding="ascii")
    parts: list[str] = []
    index = 0
    while True:
        piece = Path(f"{path}.b64.{index:02d}")
        if not piece.is_file():
            break
        parts.append(piece.read_text(encoding="ascii"))
        index += 1
    if not parts:
        raise FileNotFoundError(path)
    return "".join(parts)


def _ensure_checkpoint(path: Path) -> Path:
    if path.is_file():
        return path
    raw = base64.b64decode(_checkpoint_text(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def load_checkpoint(path: str | Path, force: bool = False):
    key = str(path)
    if not force and key in _CACHE:
        return _CACHE[key]
    from stable_baselines3 import PPO

    zip_path = _ensure_checkpoint(Path(path))
    model = PPO.load(str(zip_path), device="cpu")
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
