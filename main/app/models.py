from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base 

class User(Base):
    __tablename__= "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    scores = relationship("Score", back_populates="user")
    
    def __repr__(self):
        return f"({self.id}) ({self.username} {self.hashed_password})"

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    original_path = Column(String, nullable=False)
    processed_path  = Column(String)
    xmlmusic_path = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User", back_populates="scores")
        
    def __repr__(self):
        return f"({self.id}) ({self.original_path} {self.processed_path} {self.xmlmusic_path}) ({self.user_id})"
    