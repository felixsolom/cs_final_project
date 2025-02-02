from sqlalchemy import Column, Integer, String,  LargeBinary, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__= "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    
    def __repr__(self):
        return f"({self.id}) ({self.username} {self.hashed_password})"

class Score(Base):
    __tablename__ = "scores"
    id = Column(Integer, primary_key=True)
    binary_file = Column(LargeBinary)
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="scores")
        
    def __repr__(self):
        return f"({self.id}) ({self.binary_file})"
    