from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.errors import api_error

client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=3000)
db = client.get_default_database("creatorai")


def oid(value: str) -> ObjectId:
    """Parse an id from a path/query param; malformed ids 404 like missing ones."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise api_error(404, "Not found", "NOT_FOUND")


async def owned(collection: str, doc_id: str, user: dict) -> dict:
    """Fetch a doc the user owns (has user_id), or 404."""
    doc = await db[collection].find_one({"_id": oid(doc_id), "user_id": user["_id"]})
    if not doc:
        raise api_error(404, f"{collection.rstrip('s').replace('_', ' ').capitalize()} not found", "NOT_FOUND")
    return doc


async def owned_clip(clip_id: str, user: dict) -> dict:
    """Clips have no user_id; ownership goes through their project."""
    clip = await db.clips.find_one({"_id": oid(clip_id)})
    if not clip or not await db.projects.find_one({"_id": clip["project_id"], "user_id": user["_id"]}, {"_id": 1}):
        raise api_error(404, "Clip not found", "NOT_FOUND")
    return clip


async def ping() -> bool:
    try:
        await client.admin.command("ping")
        return True
    except Exception:
        return False


async def create_indexes() -> None:
    """Indexes from DATABASE_SCHEMA.md. create_index is idempotent."""
    await db.users.create_index("email", unique=True)
    await db.projects.create_index([("user_id", 1), ("stage", 1)])
    await db.projects.create_index([("user_id", 1), ("updated_at", -1)])
    await db.assets.create_index([("user_id", 1), ("type", 1)])
    await db.assets.create_index([("filename", "text"), ("ai.tags", "text"), ("ai.description", "text")])
    await db.clips.create_index([("project_id", 1), ("scores.overall", -1)])
    await db.embeddings.create_index([("text", "text")])  # keyword fallback when Atlas Vector Search isn't set up
    await db.embeddings.create_index("asset_id")
    await db.analytics.create_index([("user_id", 1), ("posted_at", -1)])
    await db.jobs.create_index([("user_id", 1), ("status", 1)])
    # Atlas Vector Search index on embeddings.vector is created in the Atlas UI (JSON in services/search.py).
