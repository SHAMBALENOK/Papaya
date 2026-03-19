from sqlalchemy import create_engine, Column, String, Boolean, Integer
from sqlalchemy.orm import DeclarativeBase, sessionmaker, scoped_session
from sqlalchemy import inspect, text
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
from flask_login import UserMixin
from dotenv import load_dotenv
import os

# ==================== Database Configuration ====================
load_dotenv()
# USER = os.getenv('DB_USER', 'postgres')
# PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
# HOST = os.getenv('DB_HOST', 'localhost')ыыыы
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
    min_grade = Column(Integer)
    max_grade = Column(Integer)
    min_age = Column(Integer)
    max_age = Column(Integer)
    preview_picture = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    isActive = Column(Boolean, default=True)
    createdAt = Column(String)
    updatedAt = Column(String)

Base.metadata.create_all(bind=engine)

# ==================== Inspection ====================

# def check_and_fix_events_table():
#     inspector = inspect(engine)
#     columns = [col['name'] for col in inspector.get_columns('events')]
#
#     # Если нет нужных колонок, удаляем таблицу и создаем заново
#     if 'min_grade' not in columns or 'max_grade' not in columns:
#         print("⚠️ Обнаружена несовместимая структура таблицы events. Пересоздаем...")
#         with engine.connect() as conn:
#             # Удаляем таблицу (данные событий пропадут, но это тестовые данные)
#             conn.execute(text("DROP TABLE IF EXISTS events CASCADE"))
#             conn.commit()
#
#         # Пересоздаем все таблицы (events создастся заново с правильными колонками)
#         Base.metadata.create_all(bind=engine)
#         print("✅ Таблица events пересоздана успешно.")
#     else:
#         print("✅ Структура таблицы events корректна.")

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
            min_grade=ins['min_grade'],
            max_grade=ins['max_grade'],
            min_age=ins['min_age'],
            max_age=ins['max_age'],
            preview_picture=ins['preview_picture'],
            picture=ins['picture'],
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

if not find_event_by_id('111'):
    add_event(
        {
            'id': os.getenv('INIT_EVENT_ID', '111'),
            'name': os.getenv('INIT_EVENT_NAME', 'my_events'),
            'place': os.getenv('INIT_EVENT_PLACE', 'my_place'),
            'min_grade': os.getenv('INIT_EVENT_MIN_GRADE', '1'),
            'max_grade': os.getenv('INIT_EVENT_MAX_GRADE', '11'),
            'min_age': os.getenv('INIT_EVENT_MIN_AGE', '6'),
            'max_age': os.getenv('INIT_EVENT_MAX_AGE', '17'),
        }
    )

def show_random_events(quantity: int):
    with Session() as session:
        return session.query(Events).filter(Events.isActive == True).limit(quantity).all()

def close_session():
    Session.remove()