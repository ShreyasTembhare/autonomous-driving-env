"""Websocket snapshot of the crossing. Every car already carries its decision frame."""

from __future__ import annotations

import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from sim.replay import seek
from sim.world import World

HOST_WORLD = World(seed=7)
PAUSED = False
RATE = 1.0
LOCK = threading.Lock()
CLIENTS: set[WebSocket] = set()
TRAIN = {
    "running": False,
    "mix": None,
    "step": 0,
    "budget": 0,
    "reward": None,
    "crash_rate": None,
    "ready": False,
    "checkpoint": None,
    "error": None,
}


def snapshot() -> dict:
    return HOST_WORLD.snapshot(paused=PAUSED, rate=RATE, train=dict(TRAIN))


def handle(msg: dict) -> None:
    global HOST_WORLD, PAUSED, RATE
    op = msg.get("op")
    with LOCK:
        if op == "pause":
            PAUSED = True
        elif op == "play":
            PAUSED = False
        elif op == "speed":
            value = float(msg.get("value", 1))
            RATE = value if value in (0.5, 1.0, 2.0, 4.0) else 1.0
        elif op == "reset":
            HOST_WORLD = HOST_WORLD.reset_keeping_models()
        elif op == "replay":
            index = int(msg.get("index", 0))
            log = HOST_WORLD.export_log()
            HOST_WORLD = seek(log, index)
            PAUSED = True
        elif op == "train":
            _start_train(msg)
        elif op == "drive_weights":
            _drive_weights()
        else:
            HOST_WORLD.apply(msg)


def _start_train(msg: dict) -> None:
    if TRAIN["running"]:
        return
    mix = msg.get("mix", "careful")
    if mix not in ("careful", "hurried"):
        return
    steps = max(256, min(int(msg.get("steps", 4096)), 32768))
    TRAIN.update(
        {
            "running": True,
            "mix": mix,
            "step": 0,
            "budget": steps,
            "reward": None,
            "crash_rate": None,
            "ready": False,
            "checkpoint": None,
            "error": None,
        }
    )

    def job() -> None:
        from sim.train import train_mix

        out = Path(__file__).resolve().parent / "checkpoints" / "runs" / f"{mix}-{steps}.zip"
        # A second run of the same budget would clobber the file; stamp the thread id.
        out = out.with_name(f"{mix}-{steps}-{threading.get_ident()}.zip")

        def progress(update: dict) -> None:
            TRAIN["step"] = update["step"]
            TRAIN["reward"] = update["reward"]
            TRAIN["crash_rate"] = update["crash_rate"]

        try:
            train_mix(mix, steps, seed=0, out_path=out, progress=progress)
            with LOCK:
                TRAIN["checkpoint"] = str(out)
                TRAIN["ready"] = True
                TRAIN["running"] = False
                TRAIN["step"] = steps
        except Exception as exc:  # noqa: BLE001 — surface the training error on the desk
            with LOCK:
                TRAIN["running"] = False
                TRAIN["error"] = str(exc)

    threading.Thread(target=job, daemon=True).start()


def _drive_weights() -> None:
    if not TRAIN.get("ready") or not TRAIN.get("checkpoint"):
        return
    HOST_WORLD.apply(
        {
            "op": "hot_swap",
            "mix": TRAIN["mix"],
            "checkpoint": TRAIN["checkpoint"],
            "name": Path(TRAIN["checkpoint"]).stem,
        }
    )


async def _loop() -> None:
    while True:
        with LOCK:
            if not PAUSED:
                HOST_WORLD.step()
            payload = snapshot()
            delay = 0.2 if PAUSED else 0.1 / max(RATE, 0.25)
        dead = []
        for client in list(CLIENTS):
            try:
                await client.send_json(payload)
            except Exception:
                dead.append(client)
        for client in dead:
            CLIENTS.discard(client)
        await asyncio.sleep(delay)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    task = asyncio.create_task(_loop())
    yield
    task.cancel()


app = FastAPI(title="The crossing", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "tick": HOST_WORLD.tick}


@app.websocket("/ws")
async def ws(socket: WebSocket) -> None:
    await socket.accept()
    CLIENTS.add(socket)
    try:
        with LOCK:
            await socket.send_json(snapshot())
        while True:
            message = await socket.receive_json()
            handle(message)
    except WebSocketDisconnect:
        CLIENTS.discard(socket)
    except Exception:
        CLIENTS.discard(socket)
