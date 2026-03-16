from sqlalchemy import create_engine, Column, Integer, String, Boolean, func
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from flask_login import UserMixin
import os

USER = os.getenv('DB_USER', 'postgres')
PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
HOST = os.getenv('DB_HOST', 'postgres')              # Изменено на 'db'
PORT = os.getenv('DB_PORT', '5432')            # Изменено на '5432'
DB_NAME = os.getenv('DB_NAME', 'testdb')    # Изменено на 'papaya_db'

# DATABASE_URL = os.getenv('DB_URL')

DATABASE_URL = f"postgresql://{USER}:{PASSWORD}@{HOST}:{PORT}/{DB_NAME}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=300
)
Session = sessionmaker(autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Events(Base, UserMixin):
    __tablename__ = 'events'

    id = Column(String, primary_key=True)
    name = Column(String)
    place = Column(String)
    min_grade = Column(Integer)
    max_grade = Column(Integer)
    min_age = Column(Integer)
    max_age = Column(Integer)
    isActive = Column(Boolean, default=True)
    createdAt = Column(String)
    updatedAt = Column(String)


Base.metadata.create_all(bind=engine)


def add_event(ins: dict):
    with Session(autoflush=False, bind=engine) as session:
        now = datetime.now(timezone.utc)
        formatted_time = now.isoformat().split('.')[0] + 'Z'
        event = Events(
            id=ins['id'],
            name=ins['name'],
            place=ins['place'],
            min_grade=ins['min_grade'],
            max_grade=ins['max_grade'],
            min_age=ins['min_age'],
            max_age=ins['max_age'],
            isActive=True,
            createdAt=formatted_time,
            updatedAt=formatted_time,
        )
        session.add(event)
        session.commit()
        session.refresh(event)

def find_event_by_id(event_id: str):
    with Session() as session:
        return session.query(Events).filter(Events.id == event_id).first()

if not find_event_by_id('111'):
    add_event(
        {
            'id': os.getenv('INIT_EVENT_ID', '111'),
            'name': os.getenv('INIT_EVENT_NAME', 'my_events'),
            'place': os.getenv('INIT_EVENT_PLACE', 'my_place'),
            'min_grade': os.getenv('INIT_EVENT_MIN_GRADE', '1'),
            'max_grade': os.getenv('INIT_EVENT_MAX_GRADE', '11'),
            'min_age': os.getenv('INIT_EVENT_MIN_AGE', '6'),
            'max_age': os.getenv('INIT_EVENT_MAX_AGE', '17')
        }
    )

def show_random_events(quantity: int):
    with Session() as session:
        events = session.query(Events)\
            .filter(Events.isActive == True)\
            .order_by(func.random())\
            .limit(quantity)\
            .all()
        return events