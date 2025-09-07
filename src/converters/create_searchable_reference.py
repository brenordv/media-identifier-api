from src.converters.replace_roman_numerals import replace_roman_numerals
from src.converters.special_character_remover import replace_special_chars


def create_searchable_reference(text: str):
    if text is None or text.strip() == '':
        return text

    return replace_special_chars(replace_roman_numerals(text)).strip()

