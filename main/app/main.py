import logging

from fastapi import FastAPI, File, UploadFile, Request, HTTPException, Depends, status, Form
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy.orm import Session
from .database import SessionLocal, engine
from .models import User, Score

from pydantic import BaseModel

# aux locally created functions
from .auth_utils import verify_password, create_access_token ,decode_access_token, JWTError, hash_password
from .helpers import validate_file
from .audiveris import AudiverisConverter

import cv2
import numpy as np
import fitz

#way to save data files to separate dir
from pathlib import Path


BASE_DIR = Path(__file__).parent.parent 
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

DATA_DIR.mkdir(exist_ok=True)
(DATA_DIR / "originals").mkdir(exist_ok=True, parents=True)
(DATA_DIR / "processed").mkdir(exist_ok=True, parents=True)
(DATA_DIR / "xmlmusic").mkdir(exist_ok=True, parents=True)


#fastapi boiler plate
app = FastAPI()
converter = AudiverisConverter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"], 
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

templates = Jinja2Templates(directory=TEMPLATES_DIR)



#get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        
# docker health check func
@app.get("/health")
async def health_check():
    return {"status": "Healthy"}
        
# funnction to inject user for jinja templating and check for authorization of user
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
        
    response = RedirectResponse(url="/logged_in", status_code=status.HTTP_303_SEE_OTHER)
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
    
@app.get("/logged_in")
async def index(request: Request, user: User = Depends(get_current_user)):
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return templates.TemplateResponse(
        "logged_in.html", 
        {"request": request,
        "message": f"Welcome {user.username}!"}
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
        
        convert_to_musicxml(new_score, db)  
                
        return {"message": "File processed and converted successfully"}
        
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
        if not original_file_path.is_file():
            raise ValueError(f"Original file does not exist at path: {score.original_path}")
        
        processed_dir = DATA_DIR / "processed" / f"score_{score.id}"
        processed_dir.mkdir(parents=True, exist_ok=True)
        
        file_extension = original_file_path.suffix.lower()
        logging.info(f"Proccessing file: {score.original_path} (extension: {file_extension})")
        
        if file_extension == ".pdf":
            doc = fitz.open(str(original_file_path))
            new_pdf_path = processed_dir / f"cleaned_score_{score.id}.pdf"
            new_doc = fitz.open()
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap(alpha=False)
                logging.info(f"PDF channels: {pix.n} (3=RGB, 4=RGBA)")
                    
                if not pix or pix.width == 0 or pix.height == 0:
                    raise ValueError("PDF conversion failed: Invalid page dimensions")
                
                #debug logging
                logging.info(
                    f"PDF dimensions: {pix.width}x{pix.height}, "
                    f"Pixel data size: {len(pix.samples)} bytes"
                )
                
                #verifying pixel data integrity
                expected_size = pix.width * pix.height * pix.n 
                if len(pix.samples) != expected_size:
                    raise ValueError(
                        f"Pixel data mismatch. Expected {expected_size} bytes, got {len(pix.samples)}"
                    )
                                
                # converting pixmap to numpy array for openCV processing
                image_np = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                image = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY)
                
                if image is None or image.size == 0:
                    raise ValueError(f"Page {page_num + 1}: Empty image")
                
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
                
                cleaned_image = result
                
                pix = fitz.Pixmap(
                    fitz.csGRAY, 
                    cleaned_image.shape[1], 
                    cleaned_image.shape[0],
                    cleaned_image.ravel().tobytes()
                )
                new_page = new_doc.new_page(width=cleaned_image.shape[1], height=cleaned_image.shape[0])
                
                new_page.insert_image(new_page.rect, pixmap=pix)
                
            new_doc.save(str(new_pdf_path))
            new_doc.close()
            score.processed_path = str(new_pdf_path) 
                
              #  page_path = processed_dir / f"page_{page_num + 1}.jpg"
               # cv2.imwrite(str(page_path), result)              
                
            # now taking care of non .pdf files   
        else:
            new_pdf_path = processed_dir / f"cleaned_{score.id}.pdf"
            new_doc = fitz.open()
            
            with open(original_file_path, "rb") as f:
                image_data = f.read()
                       
            image_np = np.frombuffer(image_data, dtype=np.uint8)
            image = cv2.imdecode(image_np, cv2.IMREAD_GRAYSCALE)
                
            if image is None or image.size == 0:
                raise ValueError("Failed to load image from file")
                
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
            
            cleaned_image = result
                
            pix = fitz.Pixmap(
                fitz.csGRAY, 
                cleaned_image.shape[1], 
                cleaned_image.shape[0],
                cleaned_image.ravel().tobytes()
            )
            new_page = new_doc.new_page(width=cleaned_image.shape[1], height=cleaned_image.shape[0])
                
            new_page.insert_image(new_page.rect, pixmap=pix)
                
            new_doc.save(str(new_pdf_path))
            new_doc.close()
            score.processed_path = str(new_pdf_path)        
          #  page_path = processed_dir / f"{score.id}.jpg"
          #  cv2.imwrite(str(page_path), result)
          
        db.commit()
        logging.info(f"Processing complete. Processed files saved to: {processed_dir}")
    except Exception as e:
        db.rollback()
        logging.error(f"Error during cleanup: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Processing failed") from e
        

def convert_to_musicxml(score: Score, db: Session):
    try:
        processed_file = Path(score.processed_path)
        musicxml_dir = DATA_DIR /"xmlmusic" / f"score_{score.id}"
        musicxml_dir.mkdir(parents=True, exist_ok=True)
        
        if not processed_file.exists():
            raise ValueError(f"Processed file doesn't exist at {score.processed_path}")
        
        result = converter.convert_to_musicxml(
            str(processed_file),
            str(musicxml_dir)
        )
        if result is None:
            raise ValueError(f"Conversion failed for {processed_file}")
        
        score.xmlmusic_path = result 
        db.commit()
        logging.info(f"Converting complete. MusicXML file saved to {score.xmlmusic_path}")
        
    except Exception as e:
        db.rollback()
        logging.error(f"Error during mxl conversion: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="converting failed"
            ) from e
    
