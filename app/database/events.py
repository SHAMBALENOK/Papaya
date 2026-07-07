from datetime import datetime, timezone
from typing import Any, Callable, ParamSpec, TypeVar, Coroutine

session_Spec = ParamSpec('session_Spec')
event_Return = TypeVar('event_Return')

def add_event(ins: dict, session: session_Spec, model: Callable) -> event_Return:
    """
    Функция для создания события в базе данных
    """
    event = model(
        name=ins.get('name'),
        disc=ins.get('disc'),
        owner=ins.get('owner'),
        preview_picture=ins.get('preview_picture'),
        picture=ins.get('picture'),
        createdAt=datetime.now(timezone.utc),
        updatedAt=datetime.now(timezone.utc),
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def find_event_by_id(event_id: str, session: session_Spec, model: Callable) -> event_Return:
    """
    Функция для поиска пользователя по id
    """
    return session.query(model).filter(model.id == event_id).first()

def show_random_events(quantity: int, session: session_Spec, model: Callable) -> event_Return:
    """
    Функция для показа событий
    """
    return session.query(model).filter(model.isActive == True).limit(quantity).all()

# def show_and_create_random_events(quantity: int) -> event_Return:
#     id = os.getenv('INIT_EVENT_ID', '111')
#     name = os.getenv('INIT_EVENT_NAME', 'my_events')
#     place = os.getenv('INIT_EVENT_PLACE', 'my_place')
#     min_grade = int(os.getenv('INIT_EVENT_MIN_GRADE', '1'))
#     max_grade = int(os.getenv('INIT_EVENT_MAX_GRADE', '11'))
#     min_age = int(os.getenv('INIT_EVENT_MIN_AGE', '6'))
#     max_age = int(os.getenv('INIT_EVENT_MAX_AGE', '17'))
#     preview_picture = os.getenv('INIT_EVENT_PREVIEW_PICTURE', None)
#     picture = os.getenv('INIT_EVENT_PICTURE', None)
#     with Session() as session:
#         for i in range(quantity):
#             if not find_event_by_id(id):
#                 add_event(
#                     {
#                         'id': id,
#                         'name': name,
#                         'place': place,
#                         'min_grade': min_grade,
#                         'max_grade': max_grade,
#                         'min_age': min_age,
#                         'max_age': max_age,
#                         'preview_picture': preview_picture,
#                         'picture': picture,
#                     }
#                 )
#                 id+='1'
#         else:
#             id += '1'
#         return session.query(Events).filter(Events.isActive == True).limit(quantity).all()
# не нужно?


def edit_event(event_id:str, ins:dict, session: session_Spec, model: Callable) -> event_Return:
    """
    Функция для редактирования
    """
    now = datetime.now(timezone.utc)
    event = session.query(model).filter(model.id == event_id).first()
    for key, value in ins.items():
        setattr(event, key, value)
    event.updatedAt = now
    session.commit()
    session.refresh(event)
    return event


def get_amount_of_events(session: session_Spec, model: Callable) -> int:
    """
    Функция показывающая количество событий
    """
    return len(session.query(model).all())