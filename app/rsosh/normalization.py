"""Нормализация текста ячеек и названий олимпиад.

Названия в перечнях РСОШ приходят разными способами и в разном написании:

    «Всероссийская\\nолимпиада\\nшкольников «Физтех»»   — переносы строк
    «"Всероссийская олимпиада школьников Физтех"»     — типографские кавычки
    «Всероссийская олимпиада школьников  Физтех »      — двойные пробелы
    «Всероссийская олимпиада школьников Физтех»        — «ё»/регистр

После нормализации такие варианты должны превратиться в одну запись каталога,
при этом разные олимпиады не должны склеиться. Поэтому нормализация
схлопывает пробелы, приводит «ё» к «е» и убирает крайнюю пунктуацию, но
сохраняет значимые символы названия.
"""

import re

from app.database.search import normalize_name

_CITATION = re.compile(r'^\s*(?:[-–—•*·]|\d+[.)])\s+')
_QUOTES = re.compile(r'[«»„“”"\'`‘’«»]')
_SPACES = re.compile(r'[\s\u00a0]+')
_DIGITS_ONLY = re.compile(r'^[\d\s.,%/–—-]+$')
_CODE_LIKE = re.compile(r'^[A-Za-zА-Яа-яЁё]{1,2}\s?\d{0,3}$')


def clean_cell(value) -> str:
    """Привести значение ячейки к читаемому однострочному тексту."""
    if value is None:
        return ''
    text = str(value).replace('\r\n', '\n').replace('\r', '\n')
    text = _SPACES.sub(' ', text).strip()
    text = _CITATION.sub('', text)
    return text.strip(' \t ;,')


def clean_description(value) -> str | None:
    """Описание олимпиады: сохраняем переносы строк как границы абзацев."""
    if value is None:
        return None
    text = str(value).replace('\r\n', '\n').replace('\r', '\n')
    blocks = [_SPACES.sub(' ', block).strip() for block in text.split('\n')]
    text = '\n'.join(block for block in blocks if block)
    return text or None


def is_noise(value: str) -> bool:
    """Похоже ли значение на мусор, а не на название олимпиады."""
    text = clean_cell(value)
    if not text or len(text) < 4:
        return True
    if _DIGITS_ONLY.match(text):
        return True
    if _CODE_LIKE.match(text.replace(' ', '')):
        return True
    return False


def looks_like_header(value: str) -> bool:
    """Является ли значение заголовком таблицы (а не названием олимпиады)."""
    text = clean_cell(maybe_reverse(value)).casefold().replace('ё', 'е')
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            'олимпиад',
            'наименование',
            'название',
            'перечень',
            'уровень',
            'предмет',
            'класс',
            'диплом',
            'результат',
            'статус',
            'профил',
            'код',
        )
    )


# Слова, по которым опознаётся «повёрнутая наизнанку» шапка таблицы: в части
# документов РСОШ ячейки шапки выведены зеркально (символы идут справа
# налево внутри слова). Такую ячейку нужно развернуть, иначе она и не
# опознаётся как заголовок, и попадает в каталог как «олимпиада».
_REVERSED_MARKERS = (
    'наименование',
    'название',
    'олимпиада',
    'перечень',
    'уровень',
    'предмет',
    'класс',
    'диплом',
    'результат',
    'статус',
    'профиль',
    'код',
    'приказ',
    'министерство',
    'приложение',
    'поступающ',
    'льгот',
)


def maybe_reverse(value: str) -> str:
    """Развернуть текст, если в развёрнутом виде он читается как служебный.

    Эвристика узкая и предсказуемая: разворот применяется только тогда, когда
    в исходном тексте нет ни одного опознавательного слова, а в развёрнутом
    оно есть. Обычные названия олимпиад не затрагиваются.
    """
    text = clean_cell(value)
    if not text:
        return text
    lowered = text.casefold().replace('ё', 'е')
    if any(marker in lowered for marker in _REVERSED_MARKERS):
        return text
    reversed_text = text[::-1]
    reversed_lowered = reversed_text.casefold().replace('ё', 'е')
    if any(marker in reversed_lowered for marker in _REVERSED_MARKERS):
        return reversed_text
    return text


# Служебные строки документа, которые не являются олимпиадами: шапка письма,
# реквизиты приказа, подписи, колонтитулы.
_BOILERPLATE_MARKERS = (
    'министерство',
    'федеральное государственное',
    'федеральное автономное',
    'приложение',
    'утверждено',
    'утверждаю',
    'приказ',
    'содержание',
    'оглавление',
    'страница',
    'телефон',
    'электронная почта',
    'факс',
    'подпись',
    'место печати',
    'учредитель',
)


def is_boilerplate(value: str) -> bool:
    """Служебный текст документа (шапка/реквизиты), а не название олимпиады."""
    text = clean_cell(value).casefold().replace('ё', 'е')
    return any(marker in text for marker in _BOILERPLATE_MARKERS)


def mentions_olympiad(value: str) -> bool:
    """Есть ли в названии слово «олимпиада» — основной признак записи РСОШ."""
    text = clean_cell(value).casefold().replace('ё', 'е')
    return 'олимпиад' in text


def normalize_olympiad_name(value: str) -> str:
    """Название олимпиады для каталога: человекочитаемое и устойчивое к OCR."""
    text = maybe_reverse(value)
    text = text.replace('|', ' ')
    text = _SPACES.sub(' ', text)
    return text.strip().strip('«»"“”„')


def name_key(value: str) -> str:
    """Ключ дедупликации (совпадает с ``olympiads.name_norm``)."""
    return normalize_name(value)
