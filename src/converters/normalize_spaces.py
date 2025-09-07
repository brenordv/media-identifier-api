import re


def normalize_spaces(text: str) -> str:
    """
    Replaces multiple consecutive spaces with a single space.

    Args:
        text (str): The input string that may contain multiple spaces.

    Returns:
        str: The string with normalized spacing.
    """
    return re.sub(r'\s+', ' ', text)
