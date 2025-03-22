# app/auth/apple.py
from typing import Optional
import jwt
import time
import json
from fastapi import APIRouter, Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from app.core.config import settings
import logging

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter(prefix="/auth/apple", tags=["auth"])

def create_client_secret() -> str:
    """Create client secret for Apple Sign In"""
    time_now = int(time.time())
    
    headers = {
        'kid': settings.APPLE_KEY_ID,
        'alg': 'ES256'
    }
    
    payload = {
        'iss': settings.APPLE_TEAM_ID,
        'iat': time_now,
        'exp': time_now + 86400 * 180,  # 180 days
        'aud': 'https://appleid.apple.com',
        'sub': settings.APPLE_CLIENT_ID,
    }
    
    try:
        with open(settings.APPLE_PRIVATE_KEY_PATH, 'r') as f:
            private_key = f.read()
        client_secret = jwt.encode(
            payload,
            private_key,
            algorithm='ES256',
            headers=headers
        )
        return client_secret
    except Exception as e:
        logger.error(f"Failed to create client secret: {e}")
        raise HTTPException(status_code=500, detail="Failed to create client secret")

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name='apple',
    server_metadata_url='https://appleid.apple.com/.well-known/openid-configuration',
    client_id=settings.APPLE_CLIENT_ID,
    client_secret=create_client_secret,
    client_kwargs={
        'scope': 'name email',
        'response_mode': 'form_post',
        'response_type': 'code id_token',
    }
)

@router.get("/auth")
async def apple_auth(request: Request):
    """Initialize Apple Sign In"""
    try:
        redirect_uri = request.url_for('apple_callback')
        logger.info(f"Redirect URI: {redirect_uri}")
        return await oauth.apple.authorize_redirect(request, redirect_uri)
    except Exception as e:
        logger.error(f"Apple authorization redirect failed: {e}")
        raise HTTPException(status_code=500, detail="Authorization redirect failed")

@router.post("/callback")
async def apple_callback(
    request: Request,
    code: Optional[str] = None,
    id_token: Optional[str] = None,
    user: Optional[str] = None,
    error: Optional[str] = None
):
    """Handle Apple Sign In callback"""
    if error:
        logger.error(f"Apple authentication failed: {error}")
        raise HTTPException(
            status_code=400,
            detail=f"Apple authentication failed: {error}"
        )
    
    try:
        token = await oauth.apple.authorize_access_token(request)
        logger.info(f"Authorized access token: {token}")
        
        user_info = await oauth.apple.parse_id_token(request, token)
        logger.info(f"Parsed user info: {user_info}")
        
        if user:
            try:
                user_data = json.loads(user)
                name = user_data.get('name', {})
                user_info.update({
                    'first_name': name.get('firstName'),
                    'last_name': name.get('lastName')
                })
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse user data: {e}")
                pass
        
        return {
            "access_token": token.get('access_token'),
            "refresh_token": token.get('refresh_token'),
            "id_token": id_token,
            "user": user_info
        }
    except Exception as e:
        logger.error(f"Apple callback failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

@router.post("/revoke")
async def revoke_token(token: str):
    """Revoke Apple token"""
    try:
        response = await oauth.apple.post(
            'https://appleid.apple.com/auth/revoke',
            data={
                'client_id': settings.APPLE_CLIENT_ID,
                'client_secret': create_client_secret(),
                'token': token,
            }
        )
        logger.info(f"Token revocation response: {response.json()}")
        return {"message": "Token revoked"}
    except Exception as e:
        logger.error(f"Token revocation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

@router.post("/validate")
async def validate_token(token: str):
    """Validate Apple token"""
    try:
        user_info = await oauth.apple.parse_id_token(None, {'id_token': token})
        logger.info(f"Validated user info: {user_info}")
        return user_info
    except Exception as e:
        logger.error(f"Token validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid token: {str(e)}"
        )