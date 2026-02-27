from sqlalchemy import create_engine, Column, String, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from flask_login import UserMixin
import os

# ==================== Database Configuration ====================
# USER = os.getenv('DB_USER', 'postgres')
# PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
# HOST = os.getenv('DB_HOST', 'localhost')
# PORT = os.getenv('DB_PORT', '5432')
# DB_NAME = os.getenv('DB_NAME', 'papaya_db')
#
# DATABASE_URL = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}?sslmode=require"

DATABASE_URL = os.getenv('DATABASE_URL')

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # Проверка соединения перед использованием
    pool_recycle=300,  # Переподключение через 5 минут
    pool_size=5,
    max_overflow=10
)

Session = scoped_session(sessionmaker(autoflush=False, bind=engine))


class Base(DeclarativeBase):
    pass


# ==================== Users Model ====================
class Users(Base, UserMixin):
    __tablename__ = 'users'

    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    fullname = Column(String, nullable=False)
    role = Column(String, default='USER')
    isActive = Column(Boolean, default=True)
    createdAt = Column(String)
    updatedAt = Column(String)

    def get_id(self):
        return self.id


# ==================== Events Model ====================
class Events(Base):
    __tablename__ = 'events'

    id = Column(String, primary_key=True)
    name = Column(String)
    place = Column(String)
    grade = Column(Integer)
    min_age = Column(Integer)
    max_age = Column(Integer)
    isActive = Column(Boolean, default=True)
    createdAt = Column(String)
    updatedAt = Column(String)


Base.metadata.create_all(bind=engine)

# ==================== Users Functions ====================
def add_user(ins: dict):
    with Session() as session:
        now = datetime.now(timezone.utc)
        formatted_time = now.isoformat().split('.')[0] + 'Z'
        user = Users(
            id=ins['id'],
            email=ins['email'],
            password=generate_password_hash(ins['password']),
            fullname=ins['fullname'],
            role=ins['role'],
            isActive=True,
            createdAt=formatted_time,
            updatedAt=formatted_time,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def find_user_by_email(email: str):
    with Session() as session:
        return session.query(Users).filter(Users.email == email).first()


def find_user_by_id(user_id: str):
    with Session() as session:
        return session.query(Users).filter(Users.id == user_id).first()


# ==================== Events Functions ====================
def add_event(ins: dict):
    with Session() as session:
        now = datetime.now(timezone.utc)
        formatted_time = now.isoformat().split('.')[0] + 'Z'
        event = Events(
            id=ins['id'],
            name=ins['name'],
            place=ins['place'],
            grade=ins['grade'],
            min_age=ins['min_age'],
            max_age=ins['max_age'],
            isActive=True,
            createdAt=formatted_time,
            updatedAt=formatted_time,
        )
        session.add(event)
        session.commit()
        session.refresh(event)
        return event


def find_event_by_id(event_id: str):
    with Session() as session:
        return session.query(Events).filter(Events.id == event_id).first()


def show_random_events(quantity: int):
    with Session() as session:
        return session.query(Events).filter(Events.isActive == True).limit(quantity).all()

def close_session():
    Session.remove()