from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
# import os
#
# USER = os.getenv('DB_USER')
# PASSWORD = os.getenv('DB_PASSWORD')
# HOST = os.getenv('DB_HOST')
# PORT = os.getenv('DB_PORT')
# DB_NAME = os.getenv('DB_NAME')
#
engine = create_engine(f"postgresql://postgres:pasha290410@localhost:5432/papaya_db", echo=True)
Session = sessionmaker(autoflush=False, bind=engine)

class Base(DeclarativeBase): pass

class Users(Base):
    __tablename__ = 'Users'

    id = Column(String, primary_key=True)
    email = Column(String)
    password = Column(String)
    fullname = Column(String)
    role = Column(String)
    isActive = Column(Boolean)
    createdAt = Column(String)
    updatedAt = Column(String)

Base.metadata.create_all(bind=engine)

def add_user(ins: dict):
    with Session(autoflush=False, bind=engine) as session:
        now = datetime.now(timezone.utc)
        formatted_time = now.isoformat().split('.')[0] + 'Z'
        user = Users(
            id = ins['user_id'],
            email=ins['email'],
            password=ins['password'],
            fullname=ins['fullname'],
            role=ins['role'],
            isActive= True,
            createdAt= formatted_time,
            updatedAt= formatted_time,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

def find_user(id: str):
    with Session(autoflush=False, bind=engine) as session:
        result = session.query(Users).filter(Users.id==id).first()
    return result