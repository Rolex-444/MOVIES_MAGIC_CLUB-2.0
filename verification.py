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
from verification_tokens import save_verify_token, get_verify_token

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="templates")

def generate_verify_token(length=16):
    """Generate random verification token"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

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
    Tries ALL common API formats until one works
    GOAL: Create shortlink that earns you money
    """
    # Get shortlink settings from database (admin dashboard)
    api_key, shortlink_service = await get_shortlink_settings()
    
    if not api_key or not shortlink_service:
        logger.warning("⚠️ Shortlink API/URL not configured. Using original URL.")
        logger.warning("🔧 Please configure in Admin Dashboard → Verification Settings")
        return original_url
    
    logger.info(f"🔗 Creating shortlink for: {original_url}")
    logger.info(f"🌐 Using service: {shortlink_service}")
    logger.info(f"🔑 API key: {api_key[:10]}...")
    
    # Prepare API endpoint
    api_endpoint = shortlink_service
    if not api_endpoint.startswith('http'):
        api_endpoint = f"https://{api_endpoint}"
    
    if not api_endpoint.endswith('/api'):
        if not api_endpoint.endswith('/'):
            api_endpoint += '/api'
        else:
            api_endpoint += 'api'
    
    # Try all common API formats
    api_formats = [
        # Format 1: GET with api & url parameters
        {'method': 'GET', 'params': {'api': api_key, 'url': original_url}},
        # Format 2: POST with api & url parameters
        {'method': 'POST', 'data': {'api': api_key, 'url': original_url}},
        # Format 3: GET with key & url parameters
        {'method': 'GET', 'params': {'key': api_key, 'url': original_url}},
        # Format 4: GET with token & link parameters
        {'method': 'GET', 'params': {'token': api_key, 'link': original_url}},
        # Format 5: JSON POST with Authorization header
        {'method': 'POST', 'json': {'url': original_url}, 'headers': {'Authorization': f'Bearer {api_key}'}},
        # Format 6: Form POST with api_key
        {'method': 'POST', 'data': {'api_key': api_key, 'long_url': original_url}},
        # Format 7: GET with apikey parameter
        {'method': 'GET', 'params': {'apikey': api_key, 'originalUrl': original_url}},
        # Format 8: Custom format for specific services
        {'method': 'GET', 'params': {'api': api_key, 'url': original_url, 'alias': generate_verify_token(6)}},
    ]
    
    # Try each format
    for i, format_config in enumerate(api_formats, 1):
        try:
            logger.info(f"🔄 Trying API format #{i}: {format_config['method']}")
            
            # Make request based on format
            if format_config['method'] == 'GET':
                response = requests.get(
                    api_endpoint,
                    params=format_config.get('params'),
                    headers=format_config.get('headers', {}),
                    timeout=15,
                    verify=False  # Skip SSL verification for some services
                )
            else:  # POST
                response = requests.post(
                    api_endpoint,
                    data=format_config.get('data'),
                    json=format_config.get('json'),
                    headers=format_config.get('headers', {}),
                    timeout=15,
                    verify=False
                )
            
            logger.info(f"📊 Response Status: {response.status_code}")
            logger.info(f"📄 Response: {response.text[:500]}")
            
            # Try to parse JSON response
            if response.status_code == 200:
                try:
                    data = response.json()
                    
                    # Check all possible response field names
                    possible_fields = [
                        'shortenedUrl', 'shortened_url', 'short_url', 'shortUrl',
                        'result_url', 'url', 'link', 'shortened', 'short_link',
                        'result', 'shortlink', 'short', 'data'
                    ]
                    
                    for field in possible_fields:
                        if field in data and data[field]:
                            shortlink = data[field]
                            # Extract URL if it's nested in data object
                            if isinstance(shortlink, dict) and 'url' in shortlink:
                                shortlink = shortlink['url']
                            
                            # Validate it's a proper URL
                            if isinstance(shortlink, str) and shortlink.startswith('http'):
                                logger.info(f"✅ SUCCESS! Shortlink created: {shortlink}")
                                return shortlink
                    
                    # Check if response indicates success but different format
                    if data.get('status') == 'success' or data.get('success') == True:
                        logger.info(f"📋 Success response but no URL found: {data}")
                    else:
                        logger.warning(f"⚠️ Format #{i} failed: {data}")
                        
                except ValueError:
                    # Not JSON, maybe plain text response
                    if response.text.startswith('http'):
                        logger.info(f"✅ SUCCESS! Plain text shortlink: {response.text}")
                        return response.text.strip()
                        
        except requests.exceptions.Timeout:
            logger.warning(f"⏰ Format #{i} timed out")
        except requests.exceptions.RequestException as e:
            logger.warning(f"🔌 Format #{i} connection error: {e}")
        except Exception as e:
            logger.warning(f"❌ Format #{i} error: {e}")
    
    logger.error("❌ ALL API formats failed! No shortlink created.")
    logger.error("🔧 Check your shortlink settings in Admin Dashboard")
    return original_url  # Return original URL if all attempts fail


# ========== FASTAPI ROUTES ==========

@router.get("/verify/start")
async def verify_start(request: Request, next: str = "/"):
    """
    ✅ FIXED: Step 1 - Generate verification shortlink WITH await
    """
    try:
        # Generate verification token
        token = generate_verify_token()
        
        # Save token to database
        await save_verify_token(request, token, next)
        
        # Create verification URL (where user will land after shortlink)
        base_url = str(request.base_url).rstrip('/')
        verify_url = f"{base_url}/verify/check/{token}"
        
        logger.info(f"🎯 Generated verify URL: {verify_url}")
        
        # ✅ FIX: Add await here!
        shortlink = await create_universal_shortlink(verify_url)
        
        logger.info(f"💰 Shortlink created: {shortlink}")
        
        # Return verification page with shortlink
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
    Validate token and mark user as verified
    """
    try:
        # Get token from database
        token_data = await get_verify_token(token)
        
        if not token_data:
            logger.warning(f"⚠️ Invalid or expired token: {token}")
            return templates.TemplateResponse(
                "verify_error.html",
                {
                    "request": request,
                    "message": "Verification link expired or invalid. Please try again."
                }
            )
        
        # Mark user as verified
        await mark_verified(request)
        
        # Get redirect URL
        next_url = token_data.get("redirect_url", "/")
        
        logger.info(f"✅ User verified successfully! Redirecting to: {next_url}")
        
        # Redirect to original destination
        return RedirectResponse(next_url, status_code=303)
        
    except Exception as e:
        logger.error(f"❌ Error in verify_check: {e}")
        return RedirectResponse("/")


@router.get("/verify/success")
async def verify_success(request: Request):
    """
    Success page after verification
    """
    return templates.TemplateResponse(
        "verify_success.html",
        {"request": request}
    )


# Backward compatibility functions
async def test_shortlink_api():
    """✅ UPDATED: Test your shortlink API with detailed debugging"""
    try:
        logger.info("🧪 Testing shortlink API...")
        # Test with a simple URL
        test_url = "https://google.com"
        result = await create_universal_shortlink(test_url)
        
        if result and result.startswith('http') and result != test_url:
            logger.info(f"✅ API TEST SUCCESS! Shortlink: {result}")
            return True
        else:
            logger.error(f"❌ API TEST FAILED! Result: {result}")
            return False
    except Exception as e:
        logger.error(f"❌ API test error: {e}")
        return False
    
