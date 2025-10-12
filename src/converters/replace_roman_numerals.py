import re
from typing import Iterable, Tuple

# Roman symbol values
_ROMAN_VALUES = {
    "I": 1, "V": 5, "X": 10, "L": 50,
    "C": 100, "D": 500, "M": 1000,
}

# Canonical decomposition table for 1..3999
_CANONICAL_TABLE: Iterable[Tuple[int, str]] = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"),  (90, "XC"), (50, "L"),  (40, "XL"),
    (10, "X"),   (9, "IX"),  (5, "V"),   (4, "IV"),
    (1, "I"),
]

# Token candidates: one or more roman letters bounded by word boundaries.
# NOTE: This pattern can never match an empty string.
_ROMAN_TOKEN_UPPER_RE = re.compile(r"\b[MDCLXVI]+\b")
_ROMAN_TOKEN_I_RE = re.compile(r"\b[MDCLXVI]+\b", re.IGNORECASE)


def _int_to_roman(n: int) -> str:
    """Encode 1..3999 into canonical Roman numerals."""
    if not (1 <= n <= 3999):
        raise ValueError("Value out of range (must be 1..3999)")
    out = []
    for val, sym in _CANONICAL_TABLE:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def _roman_to_int_loose(s: str) -> int:
    """
    Decode a Roman string using standard subtractive logic.
    This accepts some non-canonical forms (e.g. 'IC' => 99),
    so we *always* verify with a round-trip check afterward.
    """
    total, i = 0, 0
    while i < len(s):
        v = _ROMAN_VALUES[s[i]]
        if i + 1 < len(s):
            v_next = _ROMAN_VALUES[s[i + 1]]
            if v < v_next:
                total += v_next - v
                i += 2
                continue
        total += v
        i += 1
    return total


def replace_roman_numerals(
    text: str,
    *,
    case_insensitive: bool = False,
    skip_isolated_i: bool = True,
    convert_single_letters: bool = True,
) -> str:
    """
    Replace valid, canonical Roman numerals in `text` with their Arabic equivalents.

    Args:
        text: The text to process.
        case_insensitive: If True, convert both upper- and lowercase tokens.
        skip_isolated_i: If True, do not convert a lone 'I' (avoid pronoun).
        convert_single_letters: If False, require tokens length>=2 (avoids 'X' in "OS X").

    Behavior:
        - Only tokens made solely of roman letters [IVXLCDM]+ are candidates.
        - Token is converted only if round-trip validation holds:
            _int_to_roman(_roman_to_int_loose(token)) == token_upper
          and 1 <= value <= 3999.
    """
    pattern = _ROMAN_TOKEN_I_RE if case_insensitive else _ROMAN_TOKEN_UPPER_RE

    def _repl(m: re.Match) -> str:
        token = m.group(0)
        token_upper = token.upper()

        # Optionally skip single-letter cases
        if len(token_upper) == 1:
            if token_upper == "I" and skip_isolated_i:
                return token  # leave pronoun I alone
            if not convert_single_letters:
                return token  # leave V/X/L/C/D/M alone

        # Convert and round-trip validate
        try:
            value = _roman_to_int_loose(token_upper)
            if not (1 <= value <= 3999):
                return token
            if _int_to_roman(value) != token_upper:
                return token  # non-canonical form like 'IC'
            return str(value)
        except Exception:
            return token  # any unexpected char => leave as-is

    return pattern.sub(_repl, text)


# -------------------------
# Quick self-tests/examples
# -------------------------
if __name__ == "__main__":
    examples = [
        "I have IX apples and MMXXV coins.",  # safer: keeps "I" as pronoun
        "Chapter IV to VI is tough.",
        "The year was MCMLXXXIV.",
        "This is a mix of words.",  # unchanged (lowercase)
        "In roman: XLII; in arabic: ?",
        "Invalid forms like IC should NOT change.",
        "Edge punctuation: (XV), [X], 'IV', \"CM\"",
        "Different Cases Ii ii II"
    ]
    for s in examples:
        print(s, "=>", replace_roman_numerals(s, case_insensitive=True))

    # Case-insensitive variant (be careful in prose!)
    print(replace_roman_numerals("mix vi vii ix", case_insensitive=True))
