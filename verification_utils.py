# verification_utils.py

import secrets
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional

import pytz
from fastapi import Request

from db import get_db
from config import (
    VERIFICATION_DEFAULT_ENABLED,
    VERIFICATION_DEFAULT_FREE_LIMIT,
    VERIFICATION_DEFAULT_VALID_MINUTES,
)

IST = pytz.timezone("Asia/Kolkata")


async def get_verification_settings() -> Dict[str, Any]:
    """
    Read global verification settings from Mongo.
    Falls back to config defaults if document not present.
    """
    db = get_db()
    if db is None:
        return {
            "enabled": VERIFICATION_DEFAULT_ENABLED,
            "free_limit": VERIFICATION_DEFAULT_FREE_LIMIT,
            "valid_minutes": VERIFICATION_DEFAULT_VALID_MINUTES,
        }

    doc = await db["settings"].find_one({"_id": "verification"}) or {}
    return {
        "enabled": bool(doc.get("enabled", VERIFICATION_DEFAULT_ENABLED)),
        "free_limit": int(doc.get("free_limit", VERIFICATION_DEFAULT_FREE_LIMIT)),
        "valid_minutes": int(doc.get("valid_minutes", VERIFICATION_DEFAULT_VALID_MINUTES)),
    }


async def get_or_create_session_id(request: Request) -> str:
    """
    Use Starlette session to identify a web user.
    """
    sid = request.session.get("session_id")
    if not sid:
        sid = secrets.token_hex(16)
        request.session["session_id"] = sid
    return sid


async def get_user_verification_state(
    request: Request,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """
    Load or initialise verification state for current session_id.

    Returns: (settings, state, today_str)
      - settings: {enabled, free_limit, valid_minutes}
      - state:    {free_used, verified_until (datetime | None)}
    """
    settings = await get_verification_settings()
    db = get_db()
    today = datetime.now(IST).strftime("%Y-%m-%d")

    if db is None:
        # No DB → no restriction
        return settings, {"free_used": 0, "verified_until": None}, today

    sid = await get_or_create_session_id(request)
    col = db["verifications"]
    doc = await col.find_one({"session_id": sid})

    if not doc or doc.get("day") != today:
        # New day or first time
        state = {"free_used": 0, "verified_until": None}
        now_utc = datetime.utcnow()
        if not doc:
            await col.insert_one(
                {
                    "session_id": sid,
                    "day": today,
                    "free_used": 0,
                    "verified_until": None,
                    "updated_at": now_utc,
                }
            )
        else:
            await col.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {
                        "day": today,
                        "free_used": 0,
                        "verified_until": None,
                        "updated_at": now_utc,
                    }
                },
            )
        return settings, state, today

    verified_until = doc.get("verified_until")
    if isinstance(verified_until, str):
        try:
            verified_until = datetime.fromisoformat(verified_until)
        except Exception:
            verified_until = None

    state = {
        "free_used": int(doc.get("free_used", 0)),
        "verified_until": verified_until,
    }
    return settings, state, today


async def should_require_verification(request: Request) -> bool:
    """
    Decide if current click (watch/download) should be sent to verification.
    """
    settings, state, today = await get_user_verification_state(request)

    # Feature disabled globally → never block
    if not settings["enabled"]:
        return False

    # If still within verified window → allow
    vu: Optional[datetime] = state["verified_until"]
    if vu and datetime.utcnow() < vu:
        return False

    # If free usage not exceeded → allow
    if state["free_used"] < settings["free_limit"]:
        return False

    # Free limit finish & not currently verified
    return True


async def increment_free_used(request: Request) -> None:
    """
    Increment free_used when user actually accesses watch/download
    (after passing verification checks).
    """
    settings, state, today = await get_user_verification_state(request)
    db = get_db()
    if db is None:
        return
    sid = await get_or_create_session_id(request)
    col = db["verifications"]
    now_utc = datetime.utcnow()
    await col.update_one(
        {"session_id": sid},
        {
            "$set": {
                "day": today,
                "updated_at": now_utc,
            },
            "$inc": {"free_used": 1},
        },
        upsert=True,
    )


async def mark_verified(request: Request) -> None:
    """
    Mark current user as verified until now + settings.valid_minutes.
    """
    settings, state, today = await get_user_verification_state(request)
    db = get_db()
    if db is None:
        return
    sid = await get_or_create_session_id(request)
    col = db["verifications"]

    if settings["valid_minutes"] <= 0:
        verified_until = None
    else:
        verified_until = datetime.utcnow() + timedelta(minutes=settings["valid_minutes"])

    await col.update_one(
        {"session_id": sid},
        {
            "$set": {
                "day": today,
                "verified_until": verified_until,
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )
