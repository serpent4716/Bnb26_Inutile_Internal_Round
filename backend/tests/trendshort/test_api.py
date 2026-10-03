"""End-to-end through CreatorAi's real FastAPI app: auth, trends, a full mock run, and "Save to CreatorAi".
MongoDB is swapped for an in-memory mongomock database; Trend-to-Short runs in mock mode (no paid APIs)."""
import os
import sys
import time

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-bytes-long!!")

import pytest  # noqa: E402

mongomock_motor = pytest.importorskip("mongomock_motor")

from bson import ObjectId  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.db  # noqa: E402
import app.main  # noqa: E402
import app.services.storage  # noqa: E402
from app.services.auth import create_token  # noqa: E402
from app.trendshort.config import find_tool  # noqa: E402


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(app.services.storage, "MEDIA_DIR", tmp_path)   # keep saved assets out of the real media/
    real, db = app.db.db, mongomock_motor.AsyncMongoMockClient()["creatorai"]
    for mod in list(sys.modules.values()):   # every `from app.db import db` binding, not just app.db's
        for attr in ("db", "mongo"):
            if (mod.__name__ or "").startswith("app") and getattr(mod, attr, None) is real:
                monkeypatch.setattr(mod, attr, db)

    async def up():
        return True

    async def noop():
        return None
    monkeypatch.setattr(app.main, "ping", up)
    monkeypatch.setattr(app.main, "create_indexes", noop)
    with TestClient(app.main.app) as c:
        yield c, db


def _user(c, db, email):
    uid = ObjectId()
    c.portal.call(db.users.insert_one, {"_id": uid, "email": email, "name": email, "password_hash": "x"})
    return uid, {"Authorization": f"Bearer {create_token(str(uid))}"}


def _wait(c, h, run_id, states, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = c.get(f"/api/v1/t2s/runs/{run_id}", headers=h).json()
        if r["state"] in states and not r["busy"]:
            return r
        time.sleep(0.5)
    raise AssertionError(f"run stuck in {r['state']}")


def test_requires_auth(client):
    c, _ = client
    assert c.get("/api/v1/t2s/trends").status_code == 401
    assert c.get("/api/v1/t2s/runs").status_code == 401


def test_runs_are_private_to_their_owner(client):
    c, db = client
    _, alice = _user(c, db, "alice@example.com")
    _, bob = _user(c, db, "bob@example.com")
    idea = c.get("/api/v1/t2s/trends", headers=alice).json()["ideas"][0]
    run = c.post("/api/v1/t2s/runs", json={"trend_id": idea["id"], "mode": "review"}, headers=alice).json()
    assert c.get(f"/api/v1/t2s/runs/{run['id']}", headers=bob).status_code == 404
    assert [r["id"] for r in c.get("/api/v1/t2s/runs", headers=bob).json()] == []
    assert run["id"] in [r["id"] for r in c.get("/api/v1/t2s/runs", headers=alice).json()]
    _wait(c, alice, run["id"], {"scripting", "failed"})

    # SSE: EventSource can't send headers, so the token rides in the query string, and still only for the owner.
    events = f"/api/v1/t2s/runs/{run['id']}/events"
    assert c.get(events).status_code == 401
    assert c.get(events, params={"token": bob["Authorization"].split()[1]}).status_code == 404
    # (TestClient can't close an endless SSE stream, so check the owner's token resolves via the dependency.)
    from app.trendshort.router import user_header_or_query
    user = c.portal.call(lambda: user_header_or_query(None, alice["Authorization"].split()[1]))
    assert str(user["_id"]) == run["user_id"]


@pytest.mark.skipif(not (find_tool("ffmpeg") and find_tool("ffprobe")), reason="needs FFmpeg to render")
def test_full_run_then_save_to_creatorai(client):
    c, db = client
    uid, h = _user(c, db, "carol@example.com")
    trends = c.get("/api/v1/t2s/trends", headers=h).json()
    assert trends["ideas"], trends
    run = c.post("/api/v1/t2s/runs", json={"trend_id": trends["ideas"][0]["id"], "mode": "auto"}, headers=h).json()
    r = _wait(c, h, run["id"], {"ready_for_review", "failed"})
    assert r["state"] == "ready_for_review", r.get("error")

    video = r["stages"]["assembly"]["output"]["video_path"]
    assert c.get("/api/v1/t2s/files", params={"path": video}).status_code == 200
    assert c.get("/api/v1/t2s/files", params={"path": __file__}).status_code == 404   # no arbitrary reads

    saved = c.post(f"/api/v1/t2s/runs/{run['id']}/save", headers=h).json()
    assert saved["created"]
    again = c.post(f"/api/v1/t2s/runs/{run['id']}/save", headers=h).json()
    assert again == {"project_id": saved["project_id"], "created": False}

    project = c.get(f"/api/v1/projects/{saved['project_id']}", headers=h).json()
    assert project["stage"] == "review"
    assert project["script"]["source"] == "ai_generated" and project["script"]["lines"][0]["section"] == "hook"
    assert [a["id"] for a in project["assets"]] == [saved["asset_id"]]
    asset = project["assets"][0]
    assert asset["type"] == "video" and asset["storage_url"].startswith("/media/")
    assert asset["metadata"]["width"] == 1080 and asset["metadata"]["height"] == 1920
    assert "trend-to-short" in asset["ai"]["tags"]
