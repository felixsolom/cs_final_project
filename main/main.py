from typing import Union, Annotated

from fastapi import FastAPI, File, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates

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
"""
@app.post("/upload_sheet_music/")
async def upload_sheet_music(file: UploadFile = File(...)):
    if file.content_type not in ["application/pdf", "image/jpeg", "image/jpg", "image/png"]:
        return {"error": "Please use a valid format"}
    
    # Process the file for OMR TODO
    result = await process_omr(file)
    return {"result": result}
"""
