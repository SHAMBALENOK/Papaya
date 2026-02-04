import re

def is_valid_email(email: str) -> bool:
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    if len(email) > 254:  # Максимальная длина email по стандарту
        return False
    if ' ' in email: # нет пробелов
        return False
    if email.count('@') != 1: #одна собака
        return False
    local_part, domain = email.split('@')
    if len(local_part) > 64:  # Локальная часть не более 64 символов
        return False
    if '.' not in domain:  # Должна быть точка в домене
        return False
    if domain.startswith('.') or domain.endswith('.'):  # Точка не в начале и не в конце
        return False

    return True


import re


def is_valid_fullname(fullname: str) -> tuple[bool, str]:
    """
    Проверяет валидность ФИО (расширенная версия)

    Поддерживает:
    - Кириллицу (русский, украинский и др.)
    - Латиницу
    - Дефисы внутри слов
    - 2-4 слова

    Примеры валидных ФИО:
    - Иванов Иван
    - Иванов Иван Иванович
    - Петров-Сидоров Алексей Владимирович
    - John Doe
    - O'Connor Sarah

    :param fullname: ФИО для проверки
    :return: (is_valid, error_message)
    """
    if not fullname:
        return False, "ФИО не может быть пустым"

    fullname = fullname.strip()

    # Проверка общей длины
    if len(fullname) < 3:
        return False, "ФИО слишком короткое"

    if len(fullname) > 100:
        return False, "ФИО слишком длинное (максимум 100 символов)"

    # Проверка на запрещённые символы (кроме букв, пробелов, дефисов и апострофов)
    if re.search(r'[^\w\s\-\'а-яА-ЯёЁ]', fullname):
        return False, "ФИО содержит недопустимые символы"

    # Разбиваем на слова
    words = [w for w in fullname.split() if w]

    # Проверка количества слов
    if len(words) < 2:
        return False, "ФИО должно содержать минимум 2 слова (Фамилия Имя)"

    if len(words) > 4:
        return False, "ФИО не должно содержать более 4 слов"

    # Проверка каждого слова
    for i, word in enumerate(words):
        # Удаляем апострофы и дефисы для проверки длины
        clean_word = word.replace('-', '').replace('\'', '')

        if len(clean_word) < 2:
            return False, f"Часть ФИО '{word}' слишком короткая (минимум 2 буквы)"

        # Проверка, что слово содержит хотя бы одну букву
        if not re.search(r'[а-яА-ЯёЁa-zA-Z]', word):
            return False, f"Часть ФИО '{word}' должна содержать буквы"

        # Проверка на два дефиса подряд
        if '--' in word or "\'\'" in word:
            return False, "В ФИО не должно быть двух дефисов или апострофов подряд"

        # Проверка, что слово не начинается и не заканчивается дефисом
        if word.startswith('-') or word.endswith('-'):
            return False, f"Часть ФИО '{word}' не может начинаться или заканчиваться дефисом"

    # Проверка на наличие цифр
    if re.search(r'\d', fullname):
        return False, "ФИО не может содержать цифры"

    # Проверка на слишком много пробелов подряд
    if '  ' in fullname:
        return False, "ФИО не должно содержать несколько пробелов подряд"

    return True, ""


import re


def is_valid_password(password: str) -> tuple[bool, str]:
    """
    Проверяет валидность пароля

    Правила (настраиваемые):
    - Минимум 8 символов
    - Максимум 128 символов
    - Хотя бы одна заглавная буква
    - Хотя бы одна строчная буква
    - Хотя бы одна цифра
    - Хотя бы один спецсимвол (!@#$%^&* и др.)
    - Без пробелов

    :param password: Пароль для проверки
    :return: (is_valid, error_message)
    """
    if not password:
        return False, "Пароль не может быть пустым"

    # Проверка длины
    if len(password) < 8:
        return False, "Пароль должен содержать минимум 8 символов"

    if len(password) > 128:
        return False, "Пароль слишком длинный (максимум 128 символов)"

    # Проверка на пробелы
    if ' ' in password:
        return False, "Пароль не должен содержать пробелы"

    # Проверка на наличие заглавных букв
    if not re.search(r'[A-ZА-ЯЁ]', password):
        return False, "Пароль должен содержать хотя бы одну заглавную букву"

    # Проверка на наличие строчных букв
    if not re.search(r'[a-zа-яё]', password):
        return False, "Пароль должен содержать хотя бы одну строчную букву"

    # Проверка на наличие цифр
    if not re.search(r'\d', password):
        return False, "Пароль должен содержать хотя бы одну цифру"

    # Проверка на наличие спецсимволов
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};:"\\|,.<>/?]', password):
        return False, "Пароль должен содержать хотя бы один спецсимвол (!@#$%^&* и др.)"

    # Проверка на повторяющиеся символы (более 3 одинаковых подряд)
    if re.search(r'(.)\1{3,}', password):
        return False, "Пароль не должен содержать более 3 одинаковых символов подряд"

    # Проверка на последовательности (1234, abcd и т.д.)
    common_sequences = ['1234', 'abcd', 'qwerty', 'asdf', 'zxcv']
    for seq in common_sequences:
        if seq in password.lower():
            return False, f"Пароль содержит слабую последовательность '{seq}'"

    return True, ""