from typing import Optional

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models import User, Score, Base

from pydantic import BaseModel

# aux locally created functions
from auth_utils import verify_password, create_access_token ,decode_access_token, JWTError, hash_password

import cv2
import numpy as np

#way to save data files to separate dir
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR /"data"
DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "originals").mkdir(exist_ok=True, parents=True)
(DATA_DIR / "processed").mkdir(exist_ok=True, parents=True)


# creating sqlalchemy boiler plate    
engine = create_engine("sqlite:///scores.db", echo=True)
Base.metadata.create_all(bind=engine)    

SessionLocal = sessionmaker(bind=engine) 
  
#fastapi boiler plate
app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/data", StaticFiles(directory="DATA_DIR"), name="data")

templates = Jinja2Templates(directory="templates")


#get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# funnction to inject user for jinja templating
async def get_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    user = None
    
    if token:
        try: 
            payload = decode_access_token(token)
            user_id = payload.get("sub")
            user = db.query(User).filter(User.id == user_id).first()
        except JWTError:
            pass 
        
    request.state.user = user
    return user  

# dependency for validated users routes
async def get_current_user(user: Optional[User] = Depends(get_user_optional)) -> User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")        
        
#Login request pydantic model
class LoginRequest(BaseModel):
    username: str
    password: str
    
#register request pydantic model
class RegisterRequest(BaseModel):
    username: str
    password: str
    repeat_password: str
    
@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(
        "register.html", context={'request':request}                           
    ) 
@app.post("/register")
def register(request: Request, data: RegisterRequest, db: Session = Depends(get_db)):
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
    
    return {"message": "User created successfully"}  
       

@app.get("/login")
def login_page(request: Request):
     return templates.TemplateResponse(
        "login.html", context={'request':request}
    )
@app.post("/login")
def login(response: Response, request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail= "Invalid credentials")
        
    access_token = create_access_token(data={"sub": str(user.id)})
        
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=30*60
        )
    return {"access_token": access_token, "token_type": "bearer"}
    
  
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
                             file: UploadFile = File(None)):
    
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "No file uploaded")
    if file.content_type not in ["application/pdf", "image/jpeg", "image/jpg", "image/png"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail= "Upload a valid file")
    
    file_size = 0
    file_data  = b""
    async for chunk in file.file():
        file_size += len(chunk)
        if file_size >= MAX_FILE_SIZE:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail= "File size exceeds 10mb limit")
        file_data += chunk
        
    if file.content_type == "application/pdf":
    # Verifying PDF magic number
        if file_data[:4] != b"%PDF":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid PDF file")
                
    try:   
        new_score = Score(binary_file=file_data, user_id=user.id)
        db.add(new_score)
        db.commit()
        db.refresh(new_score)
        clean_up(new_score, db)  
            
        return {"message": "File uploaded successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
        
    
    #cleaning up the .pdf and .jpeg images using OpenCV library before proccessing further.
    
def clean_up(score: Score, db: Session):
    try:
        original_path = DATA_DIR / "originals" / f"{score.id}.pdf"
        original_path.parent.mkdir(exist_ok=True)
        original_path.write_bytes(score.binary_file)
        
        image_np = np.frombuffer(score.binary_file, np.uint8)
        image = cv2.imdecode(image_np, cv2.IMREAD_GRAYSCALE)
         #apply cleaning
        denoised = cv2.bilateralFilter(image, 9, 75, 75)
        #binarization
        binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        #Hough transform
        edges =cv2.Canny(binary, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
        if lines is not None:
            angle = np.median([line[0][1] for line in lines])
            center = tuple(np.array(binary.shape[1::-1])/2)
            rot_mat = cv2.getRotationMatrix2D(center,angle*180/np.pi-90,1.0)
            result = cv2.warpAffine(binary, rot_mat, binary.shape[1::-1], flags=cv2.INTER_LINEAR)
            
        processed_path = DATA_DIR / "processed" / f"{score.id}.jpg"
        cv2.imwrite(str(processed_path), result)
            
        score.orignal_path = str(original_path)
        score.processed_path = str(processed_path)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Processing failed") from e
      
    
"""
    # Process the file for OMR TODO
    result = await process_omr(file)
    return {"result": result}

"""