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