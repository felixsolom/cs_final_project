from fastapi import FastAPI, Request, HTTPException, status, Depends
from functools import wraps
from auth_utils import decode_access_token

def login_required(func):
    
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        auth_header = request.headers.get("Authorization")
        
        if not auth_header or not auth_header.startswith("Bearer"):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        
        token = auth_header.split("Bearer ")[-1]
        
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        kwargs["user"] = payload["sub"]
        return await func(request, *args, **kwargs)
    
    return wrapper 