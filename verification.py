"""
UNIVERSAL Shortlink Verification System
Works with ANY shortlink service - arolinks, gplinks, shrinkme, etc.
GOAL: Generate shortlinks that earn you money when users click them
✅ NOW READS SETTINGS FROM DATABASE (admin dashboard)
"""

import string
import random
import requests
import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from db import get_db
from config import SHORTLINK_API, SHORTLINK_URL  # Fallback defaults only
from verification_utils import mark_verified, get_verification_settings
from verification_tokens import create_verification_token, use_verification_token  # ✅ FIXED IMPORT

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")

def generate_verify_token(length=16):
    """Generate random verification token"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def get_session_id(request: Request) -> str:
    """Get or create session ID"""
    return request.session.get("session_id") or request.cookies.get("session_id", "unknown")

async def get_shortlink_settings():
    """
    ✅ NEW: Read shortlink API and URL from database.
    Falls back to config.py if not in DB.
    """
    db = get_db()
    if db is None:
        logger.warning("⚠️ Database not connected, using config.py defaults")
        return SHORTLINK_API or "", SHORTLINK_URL or ""
    
    try:
        settings = await db["settings"].find_one({"_id": "verification"})
        if settings:
            api = settings.get("shortlink_api", "").strip() or SHORTLINK_API or ""
            url = settings.get("shortlink_url", "").strip() or SHORTLINK_URL or ""
            logger.info(f"✅ Using shortlink settings from database")
            return api, url
        else:
            logger.info(f"ℹ️ No database settings found, using config.py defaults")
            return SHORTLINK_API or "", SHORTLINK_URL or ""
    except Exception as e:
        logger.error(f"❌ Error reading shortlink settings from DB: {e}")
        return SHORTLINK_API or "", SHORTLINK_URL or ""

async def create_universal_shortlink(original_url):
    """
    ✅ UPDATED: UNIVERSAL shortlink creator with database settings support
    """
    api_key, shortlink_service = await get_shortlink_settings()
    
    if not api_key or not shortlink_service:
        logger.warning("⚠️ Shortlink API/URL not configured.")
        return original_url
    
    logger.info(f"🔗 Creating shortlink for: {original_url}")
    
    api_endpoint = shortlink_service
    if not api_endpoint.startswith('http'):
        api_endpoint = f"https://{api_endpoint}"
    
    if not api_endpoint.endswith('/api'):
        if not api_endpoint.endswith('/'):
            api_endpoint += '/api'
        else:
            api_endpoint += 'api'
    
    api_formats = [
        {'method': 'GET', 'params': {'api': api_key, 'url': original_url}},
        {'method': 'POST', 'data': {'api': api_key, 'url': original_url}},
        {'method': 'GET', 'params': {'key': api_key, 'url': original_url}},
    ]
    
    for i, format_config in enumerate(api_formats, 1):
        try:
            if format_config['method'] == 'GET':
                response = requests.get(
                    api_endpoint,
                    params=format_config.get('params'),
                    timeout=15,
                    verify=False
                )
            else:
                response = requests.post(
                    api_endpoint,
                    data=format_config.get('data'),
                    timeout=15,
                    verify=False
                )
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    possible_fields = ['shortenedUrl', 'short_url', 'shortUrl', 'url', 'link']
                    
                    for field in possible_fields:
                        if field in data and data[field]:
                            shortlink = data[field]
                            if isinstance(shortlink, str) and shortlink.startswith('http'):
                                logger.info(f"✅ SUCCESS! Shortlink: {shortlink}")
                                return shortlink
                except ValueError:
                    if response.text.startswith('http'):
                        return response.text.strip()
        except Exception as e:
            logger.warning(f"Format #{i} error: {e}")
    
    logger.error("❌ ALL API formats failed!")
    return original_url


# ========== FASTAPI ROUTES ==========

@router.get("/verify/start")
async def verify_start(request: Request, next: str = "/"):
    """
    ✅ FIXED: Step 1 - Generate verification shortlink
    """
    try:
        # Generate verification token
        token = generate_verify_token()
        
        # ✅ FIXED: Use correct function name
        session_id = get_session_id(request)
        await create_verification_token(session_id, next)
        
        # Create verification URL
        base_url = str(request.base_url).rstrip('/')
        verify_url = f"{base_url}/verify/check/{token}"
        
        logger.info(f"🎯 Generated verify URL: {verify_url}")
        
        # ✅ FIX: Add await
        shortlink = await create_universal_shortlink(verify_url)
        
        logger.info(f"💰 Shortlink created: {shortlink}")
        
        return templates.TemplateResponse(
            "verify_start.html",
            {
                "request": request,
                "shortlink": shortlink,
                "next": next
            }
        )
    except Exception as e:
        logger.error(f"❌ Error in verify_start: {e}")
        return RedirectResponse(next or "/")


@router.get("/verify/check/{token}")
async def verify_check(request: Request, token: str):
    """
    Step 2: User lands here after completing shortlink
    """
    try:
        # ✅ FIXED: Use correct function name
        token_data = await use_verification_token(token)
        
        if not token_data:
            logger.warning(f"⚠️ Invalid or expired token: {token}")
            return templates.TemplateResponse(
                "verify_error.html",
                {
                    "request": request,
                    "message": "Verification link expired or invalid."
                }
            )
        
        # Mark user as verified
        await mark_verified(request)
        
        # Get redirect URL
        next_url = token_data.get("next", "/")
        
        logger.info(f"✅ User verified! Redirecting to: {next_url}")
        
        return RedirectResponse(next_url, status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Error in verify_check: {e}")
        return RedirectResponse("/")
        
