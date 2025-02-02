from typing import Union, Annotated

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import User, Score, Base

from pydantic import BaseModel

# aux locally created functions
from helpers import login_required
from auth_utils import verify_password, create_access_token

import cv2
import numpy as np

# creating sqlalchemy boiler plate    
engine = create_engine("sqlite:///scores.db", echo=True)
Base.metadata.create_all(bind=engine)    

SessionLocal = sessionmaker(bind=engine)  
session = SessionLocal()
  
#fastapi boiler plate
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

#get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
#Login request pydantic model
class LoginRequest(BaseModel):
    username: str
    password: str
    
class RegisterRequest(BaseModel):
    username: str
    password: str
    repeat_password: str
    
@app.post("/register")
@app.get("/register")
def register(request: Request, db: Session = Depends(get_db)):
    
 
 
@app.post("/login")
@app.get("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail= "Invalid credentials")
    
    token = create_access_token(data={"sub": user.username})
    return {"access_token": token}
    


  
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "No file uploaded")
        if file.content_type not in ["application/pdf", "image/jpeg", "image/jpg", "image/png"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "Upload a valid file")
        
        file_size = 0
        file_data  = b""
        async for chunk in file.stream():
            file_size += len(chunk)
            if file_size >= MAX_FILE_SIZE:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "File size exceeds 10mb limit")
            file_data += chunk
            
        new_score = Score(binary_file= file_data)
        session.add(new_score)
        session.commit()  
        
        return {"message": "File uploaded successfully"}
    
    return templates.TemplateResponse(
        "upload_sheet_music.html", context={'request':request}
    )
    
    #cleaning up the .pdf and .jpeg images using OpenCV library before proccessing further.
    
def clean_up():
    score_to_clean = session.query(Score).order_by(Score.id.desc().first())
    #load the image to grayscale
    image = cv2.imread(score_to_clean, cv2.IMREAD_GRAYSCALE)
    
    #apply cleaning
    denoised = cv2.bilateralFilter(image, 9, 75, 75)
    #binarization
    binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    #Hough transform
    edges =cv2.Canny(binary, 50, 150, aputureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
    if lines is not None:
        angle = np.median([line[0][1] for line in lines])
        center = tuple(np.array(binary.shape[1::-1])/2)
        rot_mat = cv2.getRotationMatrix2D(center,angle*180/np.pi-90,1.0)
        result = cv2.warpAffine(binary, rot_mat, binary.shape[1::-1], flags=cv2.INTER_LINEAR)
        
    cv2.imwrite("cleaned_up_music_score.jpg", result)
        
    
    
    
    
    
"""
    # Process the file for OMR TODO
    result = await process_omr(file)
    return {"result": result}

"""