# routes/verify.py

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from verification import generate_verify_token, create_universal_shortlink
from verification_utils import mark_verified, should_require_verification

templates = Jinja2Templates(directory="templates")
router = APIRouter()


@router.get("/verify/start", response_class=HTMLResponse)
async def verify_start(request: Request, next: str = "/"):
    # If already allowed, skip verification
    if not await should_require_verification(request):
        return RedirectResponse(next, status_code=303)

    token = generate_verify_token(16)
    # Use your own logic to build original_url for monetised shortlink
    original_url = f"https://t.me/YourBotUserName?start={token}"
    short_url = create_universal_shortlink(original_url)

    return templates.TemplateResponse(
        "verify_start.html",
        {
            "request": request,
            "short_url": short_url,
            "next": next,
        },
    )


@router.get("/verify/complete")
async def verify_complete(request: Request, next: str = "/"):
    await mark_verified(request)
    return RedirectResponse(next, status_code=303)
