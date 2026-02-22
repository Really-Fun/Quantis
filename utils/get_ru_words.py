def get_ru_words_for_number(number: int) -> str:
    """Возвращает правильное слово (трек, трека, треков) в зависимости от числа.
    Args:
        number (int): число
    Returns:
        str: число с правильным словом
    """
    if number % 100 == 11 or number % 100 == 12 or number % 100 == 13 or number % 100 == 14:
        return f"{number} треков"
    elif number % 10 == 1:
        return f"{number} трек"
    elif number % 10 == 2 or number % 10 == 3 or number % 10 == 4:
        return f"{number} трека"
    else:
        return f"{number} треков"