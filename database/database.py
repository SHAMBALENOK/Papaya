from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
import os

USER = os.getenv('DB_USER')
PASSWORD = os.getenv('DB_PASSWORD')
HOST = os.getenv('DB_HOST')
PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')

engine = create_engine(f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}", echo=False)  # echo=False в продакшене!
Session = sessionmaker(autoflush=False, bind=engine)

class Base(DeclarativeBase): pass

class Users(Base):
    __tablename__ = 'users'  # ИСПРАВЛЕНО: tablename → __tablename__
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)  # Добавлено: уникальность email
    password = Column(String, nullable=False)
    fullname = Column(String, nullable=False)
    role = Column(String, default='USER')
    isActive = Column(Boolean, default=True)
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
            password=generate_password_hash(ins['password']),
            fullname=ins['fullname'],
            role=ins['role'],
            isActive= True,
            createdAt= formatted_time,
            updatedAt= formatted_time,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

def find_user_by_email(email: str):
    with Session() as session:
        return session.query(Users).filter(Users.email == email).first()