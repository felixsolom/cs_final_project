async def get_user_optional(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    user = None
    
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
        
    request.state.user = user
    return user  

# dependency for validated users routes
async def get_current_user(request: Request, user: Optional[User] = Depends(get_user_optional)) -> User:
    if not user:
        response = Response(status_code=status.HTTP_401_UNAUTHORIZED)
        response.delete_cookie("access_token")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")        
        