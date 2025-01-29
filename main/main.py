from typing import Union, Annotated

from fastapi import FastAPI, File, UploadFile, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from pydantic import BaseModel
import cv2

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

   
@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", context={'request':request}
    )


@app.get("/upload_sheet_music/")
@app.post("/upload_sheet_music/")
async def upload_sheet_music(request: Request, file: UploadFile = File(None)):
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    if request.method == "POST":
        if not file:
            raise HTTPException(status_code= 400, detail= "No file uploaded")
        if file.content_type not in ["application/pdf", "image/jpeg", "image/jpg", "image/png"]:
            raise HTTPException(status_code= 400, detail= "Upload a valid file")
        
        file_size = 0
        file_data  = b""
        async for chunk in file.stream():
            file_size += len(chunk)
            if file_size >= MAX_FILE_SIZE:
                raise HTTPException(status_code= 400, detail= "File size exceeds 10mb limit")
            file_data += chunk  
        
        return {"message": "File uploaded successfully"}
    
    return templates.TemplateResponse(
        "upload_sheet_music.html", context={'request':request}
    )
    
    
    
    
"""
    # Process the file for OMR TODO
    result = await process_omr(file)
    return {"result": result}

"""