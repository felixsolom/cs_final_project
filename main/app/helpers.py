from fastapi import FastAPI, Request, HTTPException, status, Depends, UploadFile
from functools import wraps
from .auth_utils import decode_access_token
from magic import Magic
from tempfile import NamedTemporaryFile
from deprecated import deprecated
import numpy as np
import logging
import cv2
import fitz


@deprecated
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

@deprecated 
def pack_bits(binary_image):
    """Converting a 2D numpy binary array (0s and 255s) to a 1-bit packed byte stream."""
    # Threshold to 0s and 1s
    binary = (binary_image > 0).astype(np.uint8)
    # Calculate padding to make width a multiple of 8
    height, orig_width = binary.shape
    padded_width  = ((orig_width + 7) // 8) * 8
    if padded_width != orig_width:
        pad = padded_width - orig_width
        logging.info(f"Padding width from {orig_width} to {padded_width} adding {pad} columns on the right")
        binary = np.pad(binary, ((0, 0), (0, pad)), mode='constant', constant_values=1)
    packed_array = np.packbits(binary, axis=1, bitorder='big')
    packed_bytes = packed_array.tobytes()
    
    # DEBBUGGGG
    expected_bytes = (padded_width // 8) * height 
    actual_bytes = len(packed_bytes)

    logging.info(f"Padded image: width={padded_width}, height: {height}")
    logging.info(f"Expected bytes: {expected_bytes}, actual bytes: {actual_bytes}")

    return packed_bytes, padded_width, height



        

