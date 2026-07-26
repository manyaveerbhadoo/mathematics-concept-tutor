"""
parser.py — turns what a student types into math the computer understands.

This is Step 1 of the Math 1B bot. Nothing else works if this doesn't.

A student types:   3(x+1)^2 - log_2(8)
Python needs:      3*(x + 1)**2 - log(8, 2)

This module does that translation, safely, and explains itself when it fails.
"""

import re
import sympy
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)


class MathInputError(Exception):
    """Raised when we can't understand the student's input.

    The message is written FOR THE STUDENT, not for a developer.
    It should never say 'SyntaxError' or show a stack trace.
    """


# ---------------------------------------------------------------------------
# 1. SAFETY
# ---------------------------------------------------------------------------
# parse_expr() runs Python's eval() under the hood. Without protection a
# student could type __import__('os') and run commands on our server.
# Two layers of defense: a blocklist scan, then a locked-down namespace.

_FORBIDDEN = re.compile(
    r"(__|import|lambda|exec|eval|open|globals|locals|getattr|setattr|"
    r"compile|input|breakpoint|subprocess|os\.|sys\.)",
    re.IGNORECASE,
)

# Longest first, so 'arcsin' is matched before 'sin'.
_MAX_LENGTH = 500


def _log_any_base(x, b=10):
    """In pre-calculus, `log(x)` means base 10 and `ln(x)` means base e.

    SymPy's default `log` is natural log, which would silently give students
    wrong feedback. This wrapper fixes the convention:
        log(x)      -> base 10
        log(x, 2)   -> base 2
        ln(x)       -> natural   (mapped separately below)
    """
    return sympy.log(x, b)


def _log_any_base_raw(x, b=10, **kwargs):
    """Same, but refuses to compute. See STRUCTURAL MODE below.

    The **kwargs swallows the evaluate=False that structural parsing injects
    into every function call.
    """
    return sympy.log(x, b, evaluate=False)


def _unevaluated(fn):
    def wrapper(*args, **kwargs):
        return fn(*args, evaluate=False)
    return wrapper


# The ONLY names a student's input is allowed to resolve to.
_ALLOWED = {
    # trig
    "sin": sympy.sin, "cos": sympy.cos, "tan": sympy.tan,
    "sec": sympy.sec, "csc": sympy.csc, "cot": sympy.cot,
    # inverse trig (both spellings students use)
    "asin": sympy.asin, "acos": sympy.acos, "atan": sympy.atan,
    "arcsin": sympy.asin, "arccos": sympy.acos, "arctan": sympy.atan,
    # logs and roots
    "log": _log_any_base, "ln": sympy.log, "exp": sympy.exp,
    "sqrt": sympy.sqrt, "cbrt": sympy.cbrt,
    "abs": sympy.Abs, "Abs": sympy.Abs,
    # constants
    "pi": sympy.pi, "e": sympy.E, "E": sympy.E,
    "oo": sympy.oo, "infinity": sympy.oo,
}

# SymPy's transformations rewrite "2x" into Integer(2)*Symbol('x') and then
# eval() that string. So these constructors MUST exist in the namespace or
# every parse dies with NameError. This is the smallest set that works --
# it contains no Python builtins, so injection is still blocked.
_SAFE_GLOBALS = {
    "Integer": sympy.Integer,
    "Float": sympy.Float,
    "Rational": sympy.Rational,
    "Symbol": sympy.Symbol,
    "Function": sympy.Function,
    # structural mode rewrites  a + b  into  Add(a, b, evaluate=False),
    # so these three must be reachable too. Still no Python builtins here.
    "Add": sympy.Add,
    "Mul": sympy.Mul,
    "Pow": sympy.Pow,
}

# ---------------------------------------------------------------------------
# STRUCTURAL MODE
# ---------------------------------------------------------------------------
# SymPy simplifies while it parses. "3(x+2)" becomes 3*x+6 before we ever see
# it, and "log_2(8)" becomes 3. That is fine for doing math, but it destroys
# the SHAPE of what the student wrote -- and the shape is exactly what tells
# us which idea they were using.
#
# So we parse twice, for two different jobs:
#   parse_student(s)                  -> math mode, values computed
#   parse_student(s, structural=True) -> shape mode, nothing computed
#
# The detector uses shape mode. Everything else uses math mode.

_ALLOWED_STRUCTURAL = dict(_ALLOWED)
_ALLOWED_STRUCTURAL.update({
    "log": _log_any_base_raw,
    "ln": _unevaluated(sympy.log),
    "sin": _unevaluated(sympy.sin), "cos": _unevaluated(sympy.cos),
    "tan": _unevaluated(sympy.tan), "sec": _unevaluated(sympy.sec),
    "csc": _unevaluated(sympy.csc), "cot": _unevaluated(sympy.cot),
    "abs": _unevaluated(sympy.Abs), "Abs": _unevaluated(sympy.Abs),
})


# ---------------------------------------------------------------------------
# 2. NORMALIZATION
# ---------------------------------------------------------------------------
# Students paste from PDFs, phones, and Word. That drags in characters that
# look like math but aren't the ASCII ones Python expects.

_CHAR_FIXES = {
    "−": "-",   # unicode minus, extremely common in pasted PDFs
    "–": "-", "—": "-",           # en dash, em dash
    "×": "*", "⋅": "*", "·": "*",  # × ⋅ ·
    "÷": "/",                           # ÷
    "√": "sqrt",                        # √
    "π": "pi", "θ": "theta",       # π θ
    "≠": "!=", "≤": "<=", "≥": ">=",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    " ": " ",                           # non-breaking space
    "​": "",                            # zero-width space
}

# Superscript digits: x² -> x^2
_SUPERSCRIPTS = {
    "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4",
    "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9",
}


def normalize(text: str) -> str:
    """Clean up human notation into something parse_expr can handle."""
    s = text.strip()

    for bad, good in _CHAR_FIXES.items():
        s = s.replace(bad, good)

    # x² -> x^2   (insert the caret before a run of superscript digits)
    out = []
    for ch in s:
        if ch in _SUPERSCRIPTS:
            if not (out and out[-1] == "^") and not (out and out[-1].isdigit() and len(out) >= 2 and out[-2] == "^"):
                out.append("^")
            out.append(_SUPERSCRIPTS[ch])
        else:
            out.append(ch)
    s = "".join(out)

    # log_2(x) and log₂(x) -> log(x, 2)
    s = re.sub(r"log_?\{?(\d+)\}?\s*\(([^()]*)\)", r"log(\2, \1)", s)
    # log2(x) -> log(x, 2)   (no underscore; students do this constantly)
    s = re.sub(r"log(\d+)\s*\(([^()]*)\)", r"log(\2, \1)", s)

    # |x - 3| -> abs(x - 3)   (single level of nesting, which covers Math 1B)
    while "|" in s:
        m = re.search(r"\|([^|]*)\|", s)
        if not m:
            raise MathInputError(
                "You have an unmatched `|`. Absolute value needs two, like `|x - 3|`."
            )
        s = s[: m.start()] + "abs(" + m.group(1) + ")" + s[m.end():]

    # sqrt x -> sqrt(x)  when a student omits the parentheses
    s = re.sub(r"sqrt\s+([a-zA-Z0-9]+)", r"sqrt(\1)", s)

    return s


# ---------------------------------------------------------------------------
# 3. PARSING
# ---------------------------------------------------------------------------

_TRANSFORMS = standard_transformations + (
    implicit_multiplication_application,  # lets "2x" and "3(x+1)" work
    convert_xor,                          # lets "^" mean "to the power of"
)


def _check_parens(s: str) -> None:
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                raise MathInputError(
                    "There's a `)` without a matching `(`. Check your parentheses."
                )
    if depth > 0:
        raise MathInputError(
            f"You're missing {depth} closing parenthesis. Count your `(` and `)`."
        )


def parse_student(text: str, structural: bool = False):
    """Convert a student's typed math into a SymPy expression.

    structural=False (default) -> normal math mode, values computed.
    structural=True            -> preserves the shape the student typed,
                                  which is what the concept detector reads.

    Raises MathInputError with a student-friendly message on bad input.
    """
    if text is None or not text.strip():
        raise MathInputError("You didn't type anything for me to look at.")

    if len(text) > _MAX_LENGTH:
        raise MathInputError(
            f"That's longer than {_MAX_LENGTH} characters. Try one step at a time."
        )

    if _FORBIDDEN.search(text):
        raise MathInputError("That doesn't look like math. Try typing just the expression.")

    s = normalize(text)
    _check_parens(s)

    if "=" in s:
        raise MathInputError(
            "I got an `=` sign. Send me just one side at a time, "
            "or use the equation mode."
        )

    try:
        expr = parse_expr(
            s,
            transformations=_TRANSFORMS,
            local_dict=_ALLOWED_STRUCTURAL if structural else _ALLOWED,
            global_dict=_SAFE_GLOBALS,   # <-- no builtins reachable from here
            evaluate=not structural,
        )
    except MathInputError:
        raise
    except Exception:
        raise MathInputError(
            f"I couldn't read `{text.strip()}`. Common fixes: use `*` for "
            "multiplication, `^` for powers, and check your parentheses."
        )

    if not isinstance(expr, sympy.Basic):
        raise MathInputError(f"I couldn't read `{text.strip()}` as a math expression.")

    return expr


def parse_equation(text: str):
    """Parse `left = right` into a SymPy Eq object."""
    if text.count("=") != 1:
        raise MathInputError("An equation needs exactly one `=` sign.")
    left, right = text.split("=")
    return sympy.Eq(parse_student(left), parse_student(right))
