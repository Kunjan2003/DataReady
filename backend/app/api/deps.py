from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.services.auth import token_user_id
from app.models.models import User

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "): raise HTTPException(401, "Sign in to continue")
    try: user_id = token_user_id(authorization.split(" ", 1)[1])
    except ValueError: raise HTTPException(401, "Session expired. Please sign in again.")
    user = db.get(User, user_id)
    if not user: raise HTTPException(401, "Account not found")
    return user
