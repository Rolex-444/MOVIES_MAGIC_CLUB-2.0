# routes/verify.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from verification import create_universal_shortlink
from verification_utils import (
    should_require_verification,
    mark_verified,
    get_or_create_session_id,
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
    whose final destination is that callback URL (no Telegram).
    """
    # If verification not required (already verified / free), skip
    if not await should_require_verification(request):
        return RedirectResponse(next, status_code=303)

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
        },
    )


@router.get("/verify/auto")
async def verify_auto(request: Request, token: str):
    """
    Auto-verification callback.
    Called by browser after shortlink redirects back to website.
    """
    doc = await use_verification_token(token)
    if not doc:
        # Invalid / already used / expired token -> send home
        return RedirectResponse("/", status_code=303)

    # Mark this browser session as verified
    await mark_verified(request)

    next_url = doc.get("next") or "/"
    return RedirectResponse(next_url, status_code=303)

@router.get("/verify/reset-dev")
async def verify_reset_dev(request: Request):
    db = get_db()
    if db is None:
        return RedirectResponse("/", status_code=303)

    sid = await get_or_create_session_id(request)
    await db["verifications"].delete_one({"session_id": sid})
    return RedirectResponse("/", status_code=303)
    
