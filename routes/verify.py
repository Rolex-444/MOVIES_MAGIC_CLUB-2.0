# routes/verify.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from verification import create_universal_shortlink
from verification_utils import (
    should_require_verification,
    mark_verified,
    get_or_create_session_id,
    get_verification_settings,
)
from verification_tokens import (
    create_verification_token,
    use_verification_token,
)

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/verify/start", response_class=HTMLResponse)
async def verify_start(request: Request, next: str = "/"):
    """
    Entry point when user exceeded free limit.
    Generates a one-time token + callback URL, then creates a monetized shortlink
    whose final destination is that callback URL.
    """
    # If verification not required (already verified / free), skip
    if not await should_require_verification(request):
        return RedirectResponse(next, status_code=303)

    # Global settings for nice text (daily limit + validity)
    settings = await get_verification_settings()
    daily_limit = settings["free_limit"]
    valid_minutes = settings["valid_minutes"]
    valid_hours = valid_minutes // 60 if valid_minutes > 0 else 0

    # Bind token to current session and target URL
    session_id = await get_or_create_session_id(request)
    token = await create_verification_token(session_id, next)

    # Where user must land after finishing shortlink
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    callback_url = f"{base_url}/verify/auto?token={token}"

    # Create monetized shortlink that redirects to callback_url
    short_url = create_universal_shortlink(callback_url)

    return templates.TemplateResponse(
        "verify_start.html",
        {
            "request": request,
            "short_url": short_url,
            "daily_limit": daily_limit,
            "valid_hours": valid_hours,
        },
    )


@router.get("/verify/auto", response_class=HTMLResponse)
async def verify_auto(request: Request, token: str):
    """
    Auto-verification callback.
    Called by browser after shortlink redirects back to website.
    Instead of direct redirect, we show a success popup with a button.
    """
    doc = await use_verification_token(token)
    if not doc:
        # Invalid / already used / expired token -> send home
        return RedirectResponse("/", status_code=303)

    # Mark this browser session as verified
    await mark_verified(request)

    settings = await get_verification_settings()
    daily_limit = settings["free_limit"]
    valid_minutes = settings["valid_minutes"]
    valid_hours = valid_minutes // 60 if valid_minutes > 0 else 0

    next_url = doc.get("next") or "/"

    return templates.TemplateResponse(
        "verify_success.html",
        {
            "request": request,
            "next_url": next_url,
            "daily_limit": daily_limit,
            "valid_hours": valid_hours,
        },
    )
    
