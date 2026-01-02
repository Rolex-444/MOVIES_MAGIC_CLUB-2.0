from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from datetime import datetime
from bson import ObjectId
from db import get_db

router = APIRouter()

# ==================== POST COMMENT ====================
@router.post("/api/comments/add")
async def add_comment(
    content_type: str = Form(...),  # "movie" or "episode"
    content_id: str = Form(...),
    user_name: str = Form(...),
    message: str = Form(...)
):
    """
    Add a comment to a movie or episode
    """
    try:
        db = get_db()
        
        # Validate inputs
        if not user_name or len(user_name.strip()) < 2:
            return JSONResponse({
                "success": False,
                "error": "Name must be at least 2 characters"
            }, status_code=400)
        
        if not message or len(message.strip()) < 3:
            return JSONResponse({
                "success": False,
                "error": "Comment must be at least 3 characters"
            }, status_code=400)
        
        if content_type not in ["movie", "episode"]:
            return JSONResponse({
                "success": False,
                "error": "Invalid content type"
            }, status_code=400)
        
        # Create comment document
        comment = {
            "content_type": content_type,
            "content_id": content_id,
            "user_name": user_name.strip(),
            "message": message.strip(),
            "created_at": datetime.utcnow(),
            "status": "approved"  # Auto-approve for now (can add moderation later)
        }
        
        # Insert to database
        result = await db.comments.insert_one(comment)
        
        return JSONResponse({
            "success": True,
            "message": "Comment posted successfully!",
            "comment_id": str(result.inserted_id)
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to add comment: {e}")
        return JSONResponse({
            "success": False,
            "error": "Failed to post comment. Please try again."
        }, status_code=500)


# ==================== GET COMMENTS FOR CONTENT ====================
@router.get("/api/comments/{content_type}/{content_id}")
async def get_comments(content_type: str, content_id: str):
    """
    Get all approved comments for a movie or episode
    """
    try:
        db = get_db()
        
        # Validate content type
        if content_type not in ["movie", "episode"]:
            raise HTTPException(status_code=400, detail="Invalid content type")
        
        # Fetch comments from database
        comments_cursor = db.comments.find({
            "content_type": content_type,
            "content_id": content_id,
            "status": "approved"
        }).sort("created_at", -1)  # Most recent first
        
        comments = []
        async for comment in comments_cursor:
            comments.append({
                "id": str(comment["_id"]),
                "user_name": comment.get("user_name", "Anonymous"),
                "message": comment.get("message", ""),
                "created_at": comment.get("created_at").isoformat() if comment.get("created_at") else None,
                "time_ago": get_time_ago(comment.get("created_at"))
            })
        
        return JSONResponse({
            "success": True,
            "comments": comments,
            "count": len(comments)
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch comments: {e}")
        return JSONResponse({
            "success": False,
            "error": "Failed to load comments"
        }, status_code=500)


# ==================== HELPER FUNCTION ====================
def get_time_ago(dt):
    """Convert datetime to 'time ago' format"""
    if not dt:
        return "Just now"
    
    now = datetime.utcnow()
    diff = now - dt
    
    seconds = diff.total_seconds()
    
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"
    else:
        weeks = int(seconds / 604800)
        return f"{weeks} week{'s' if weeks != 1 else ''} ago"


# ==================== DELETE COMMENT (ADMIN ONLY - OPTIONAL) ====================
@router.post("/api/comments/delete/{comment_id}")
async def delete_comment(comment_id: str, request: Request):
    """
    Delete a comment (admin only)
    """
    try:
        # Check if user is admin
        admin_logged_in = request.session.get("admin_logged_in", False)
        if not admin_logged_in:
            return JSONResponse({
                "success": False,
                "error": "Unauthorized"
            }, status_code=403)
        
        db = get_db()
        
        # Delete comment
        result = await db.comments.delete_one({"_id": ObjectId(comment_id)})
        
        if result.deleted_count > 0:
            return JSONResponse({
                "success": True,
                "message": "Comment deleted successfully"
            })
        else:
            return JSONResponse({
                "success": False,
                "error": "Comment not found"
            }, status_code=404)
        
    except Exception as e:
        print(f"[ERROR] Failed to delete comment: {e}")
        return JSONResponse({
            "success": False,
            "error": "Failed to delete comment"
        }, status_code=500)
