from src.converters.normalize_spaces import normalize_spaces
from src.converters.replace_roman_numerals import replace_roman_numerals
from src.converters.special_character_remover import replace_special_chars
from src.utils import get_otel_log_handler

_logger = get_otel_log_handler("Converters")


@_logger.trace("create_searchable_reference")
def create_searchable_reference(text: str):
    if text is None or text.strip() == '':
        return text

    return normalize_spaces(replace_special_chars(replace_roman_numerals(text, case_insensitive=True))).strip()

