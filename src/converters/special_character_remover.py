import re

def replace_special_chars(text: str, replacement: str = " ", keep_spaces: bool = True) -> str:
    """
    Replace all special characters in a string with a given replacement character.

    Args:
        text (str): The input string.
        replacement (str): The character to replace specials with (default: '_').
        keep_spaces (bool): If True, spaces will be preserved instead of replaced.

    Returns:
        str: The processed string with special characters replaced.
    """
    if keep_spaces:
        # Replace anything that's not alphanumeric, space, or digit
        pattern = r"[^a-zA-Z0-9\s]"
    else:
        # Replace anything that's not alphanumeric or digit
        pattern = r"[^a-zA-Z0-9]"

    return re.sub(pattern, replacement, text)
