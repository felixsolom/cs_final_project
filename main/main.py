from typing import Optional
import logging

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends, status, Form
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import User, Score, Base

from pydantic import BaseModel

# aux locally created functions
from auth_utils import verify_password, create_access_token ,decode_access_token, JWTError, hash_password
from helpers import validate_file

import cv2
import numpy as np
import fitz

#way to save data files to separate dir
from pathlib import Path


BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR /"data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "originals").mkdir(exist_ok=True, parents=True)
(DATA_DIR / "processed").mkdir(exist_ok=True, parents=True)

# database URL
DATABASE_URL = "sqlite:///./scores.db" 

# creating sqlalchemy boiler plate    
engine = create_engine(DATABASE_URL, echo=True)
# Base.metadata.create_all(bind=engine)    

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) 

#fastapi boiler plate
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

templates = Jinja2Templates(directory="templates")


#get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# funnction to inject user for jinja templating
async def get_current_user(request: Request, db: Session = Depends(get_db)):   
    token = request.cookies.get("access_token")
    if token:
        try: 
            token = token.replace("Bearer ", "")
            payload = decode_access_token(token)
            print(f"Decoded payload: {payload}")
            user_id = int(payload.get("sub"))
            user = db.query(User).filter(User.id == user_id).first()
            print(f"User fetched: {user}")
        except JWTError:
            pass
        
    if not user:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        response.delete_cookie("access_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")         
        
    request.state.user = user
    return user  
    
        
#Login request pydantic model
class LoginRequest(BaseModel):
    username: str
    password: str
    
    class Config:
        orm_mode = True
        
    @classmethod
    def as_form(
        cls,
        username: str = Form(...),
        password: str = Form(...),
    ) -> "LoginRequest":
        return cls(username=username, password=password)
    
#register request pydantic model
class RegisterRequest(BaseModel):
    username: str
    password: str
    repeat_password: str
    
    class Config:
        orm_mode = True
        
    @classmethod
    def as_form(
        cls,
        username: str = Form(...),
        password: str = Form(...),
        repeat_password: str = Form(...), 
    ) -> "RegisterRequest":
        return cls(username=username, password=password, repeat_password=repeat_password)
    
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", context={'request':request}                           
    ) 
@app.post("/register")
def register(request: Request, data: RegisterRequest = Depends(RegisterRequest.as_form), db: Session = Depends(get_db)):
    if data.password != data.repeat_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    if not data.username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Please enter a username")
    
    existing_user = db.query(User).filter(User.username == data.username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    
    hashed_password = hash_password(data.password)
    new_user = User(username=data.username, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    
    return templates.TemplateResponse(
        "login.html", context={'request':request,
        "message": "User created successfully"}
        )
    
    
@app.get("/login")
def login_page(request: Request):
     return templates.TemplateResponse(
        "login.html", context={'request':request}
    )
@app.post("/login")
def login(response: Response, request: Request, data: LoginRequest = Depends(LoginRequest.as_form), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail= "Invalid credentials")
        
    access_token = create_access_token(data={"sub": str(user.id)})
        
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=30*60,
        samesite="Lax",
        secure=False,
        path="/",
    )
    return response
  

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        "index.html", context={'request':request}
    )

@app.get("/upload_sheet_music/")
async def upload_sheet_music_page(request: Request, user: User = Depends(get_current_user)):      
    return templates.TemplateResponse(
    "upload_sheet_music.html", context={'request':request}
    )
@app.post("/upload_sheet_music/")
async def upload_sheet_music(request: Request, 
                             user: User = Depends(get_current_user),
                             db: Session = Depends(get_db), 
                             file: UploadFile = File(...)):
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
  #  if user is None:
   #     raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not authenticated")
    
    try:
        print(f"Received file: {file.filename}, type: {file.content_type}, size: {file.size}")
    
        file_type = await validate_file(file)
        
        if file_type not in ["application/pdf", "image/jpeg", "image/jpg", "image/png"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "Upload a valid file")
        
        file_size = 0
        file_location = DATA_DIR / "originals" / file.filename
        with open(file_location, "wb") as buffer:
            while chunk := await file.read(1024):
                file_size += len(chunk)
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail= "File size exceeds 10mb limit")
                buffer.write(chunk)
                    
        try:
            file_location = str(file_location)
            new_score = Score(original_path=file_location, user_id=user.id)
            db.add(new_score)
            db.commit()
            db.refresh(new_score)
            db.flush
        except Exception as e:
            db.rollback()
            print(f"Error during commit {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error accurred while saving to the database: {str(e)}"
            )
        clean_up(new_score, db)  
                
        return {"message": "File uploaded successfully"}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"An unexpected error occured: {str(e)}"
            )
        
    
    #cleaning up the .pdf and .jpeg images using OpenCV library before proccessing further.
    
def clean_up(score: Score, db: Session):
    try:
        original_file_path = Path(score.original_path)
        if not original_file_path.is_file:
            raise ValueError(f"Original file does not exist at path: {score.original_path}")
        
        file_extension = original_file_path.suffix.lower()
        logging.info(f"Proccessing file: {score.original_path} (extension: {file_extension})")
        
        if file_extension == ".pdf":
            doc = fitz.open(str(original_file_path))
            page = doc.load_page(0)
            pix = page.get_pixmap()
                
            if not pix:
                raise ValueError("PDF conversion failed")
            
            # converting pixmap to numpy array for openCV processing
            image_np = np.array(pix.samples).reshape(pix.height, pix.width, 4)
            image = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
            
            if not image:
                raise ValueError("PDF conversion failed")
            
        else:
            with open(original_file_path, "rb") as f:
                image_data = f.read()   
            image_np = np.frombuffer(image_data, np.uint8)
            image = cv2.imdecode(image_np, cv2.IMREAD_GRAYSCALE)
         #apply cleaning
        denoised = cv2.bilateralFilter(image, 9, 75, 75)
        #binarization
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        #Hough transform
        edges =cv2.Canny(binary, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        if lines is not None:
            angles = [line[0][1] for line in lines]
            median_angle = np.degrees(np.median(angles))
            center = (image.shape[1]//2, image.shape[0]//2)
            rot_mat = cv2.getRotationMatrix2D(center, median_angle -90, 1.0)
            result = cv2.warpAffine(binary, rot_mat, 
                                    (image.shape[1], image.shape[0]), 
                                    flags=cv2.INTER_LINEAR)
        else:
            result = binary 
            
        processed_path = DATA_DIR / "processed" / f"{score.id}.jpg"
        cv2.imwrite(str(processed_path), result)
        score.processed_path = str(processed_path)
        db.commit()
        logging.info(f"Processing complete. Processed file saved to: {processed_path}")
    except Exception as e:
        db.rollback()
        logging.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Processing failed") from e
      
    
"""
    # Process the file for OMR TODO
    result = await process_omr(file)
    return {"result": result}

"""