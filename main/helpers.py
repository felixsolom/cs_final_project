from fastapi import FastAPI, Request, HTTPException, status, Depends, UploadFile
from functools import wraps
from auth_utils import decode_access_token
from magic import Magic
from tempfile import NamedTemporaryFile

def login_required(func):
    
    @wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        token = request.cookies.get("access_token")
        
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
        
        if token.startswith("Bearer "):
            token = token.split("Bearer ")[-1]
        
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
        request.state.user = {
            "username": payload["sub"],
            "id": payload.get("user_id")
        }
        
        return await func(request, *args, **kwargs)
    
    return wrapper 

async def validate_file(file: UploadFile):
    with NamedTemporaryFile(delete=True) as tmp:
        content = await file.read(2048)
        tmp.write(content)
        tmp.flush()
        mime = Magic(mime=True)
        file_type = mime.from_file(tmp.name)
    
    await file.seek(0)
    return file_type
    

