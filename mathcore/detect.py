"""
detect.py — works out WHICH IDEA a student was reaching for.

Student sends two steps of their own work:
    before:  x^2 - 5x + 6
    after:   (x - 2)(x - 3)

This module answers: "that's factoring a quadratic." The bot then teaches
factoring a quadratic, with different numbers.

DESIGN RULE, and the reason this is safe to deploy:
    We detect INTENT from structural shape, never correctness.
    Nothing here ever reports whether the student's step is right or wrong.
    A student cannot guess answers at it, because it never says "yes".
"""

from dataclasses import dataclass
import sympy
from sympy import Add, Mul, Pow, Symbol, Integer, Rational, log, sin, cos, Abs


@dataclass
class Detection:
    concept_id: str
    confidence: float
    note: str = ""


# ---------------------------------------------------------------------------
# small structural helpers
# ---------------------------------------------------------------------------

def _free_symbol(*exprs):
    for e in exprs:
        for s in sorted(e.free_symbols, key=lambda s: s.name):
            return s
    return Symbol("x")


def _logs_in(e):
    return [n for n in e.atoms(log)]


def _neg_powers(e):
    """Parts of `e` sitting in a denominator.

    SymPy has no division node -- `a/b` is stored as `a * b^(-1)`. In
    structural mode nothing gets normalized, so we have to spot those
    negative exponents ourselves rather than relying on together()/fraction().
    """
    if isinstance(e, Mul):
        return [a for a in e.args
                if isinstance(a, Pow) and a.exp.is_number and a.exp.is_negative]
    if isinstance(e, Pow) and e.exp.is_number and e.exp.is_negative:
        return [e]
    return []


def _is_fraction(e):
    """True if the expression genuinely has something in a denominator."""
    if _neg_powers(e):
        return True
    try:
        n, d = sympy.fraction(sympy.together(e))
        return d != 1
    except Exception:
        return False


def _base_symbol(e):
    """Strip powers down to the underlying symbol; None if it's mixed."""
    while isinstance(e, Pow):
        e = e.base
    return e if isinstance(e, Symbol) else None


def _numer_parts(e):
    if isinstance(e, Mul):
        neg = set(map(id, _neg_powers(e)))
        return [a for a in e.args if id(a) not in neg]
    return [e]


def _degree(e, x):
    try:
        p = sympy.Poly(e, x)
        return p.degree()
    except Exception:
        return None


def _is_perfect_square(term, x):
    """Return the square root of `term` if it is a perfect square, else None."""
    term = sympy.sympify(term)
    if term.is_number:
        if term.is_negative:
            return None
        r = sympy.sqrt(term)
        return r if r.is_rational else None
    if isinstance(term, Pow) and term.exp == 2:
        return term.base
    if isinstance(term, Mul):
        coeff, rest = term.as_coeff_Mul()
        if coeff.is_number and coeff.is_positive:
            rc = sympy.sqrt(coeff)
            rr = _is_perfect_square(rest, x)
            if rc.is_rational and rr is not None:
                return rc * rr
    return None


def _count_terms(e):
    return len(e.args) if isinstance(e, Add) else 1


def _is_product_of_sums(e):
    return isinstance(e, Mul) and sum(1 for a in e.args if isinstance(a, Add)) >= 2


def _has_symbolic_exponent(e):
    return any(isinstance(n, Pow) and n.exp.free_symbols for n in e.atoms(Pow))


def _same_base_powers(e, x):
    """Does e multiply/divide powers of the same base? e.g. x^3 * x^4"""
    if not isinstance(e, Mul):
        return False
    bases = []
    for a in e.args:
        if isinstance(a, Pow):
            bases.append(a.base)
        elif a.free_symbols:
            bases.append(a)
    return len(bases) >= 2 and len(set(map(str, bases))) == 1


# ---------------------------------------------------------------------------
# individual detectors — most specific first
# ---------------------------------------------------------------------------
# Each returns a Detection or None. They look at SHAPE, not at whether the
# student got it right.

def _d_pythagorean(b, a, x):
    sins = {n for n in b.atoms(Pow) if n.base.func is sin and n.exp == 2}
    coss = {n for n in b.atoms(Pow) if n.base.func is cos and n.exp == 2}
    has_trig_sq = bool(sins or coss)
    if not has_trig_sq:
        return None
    # sin^2 + cos^2 collapsing, or 1 - sin^2 turning into cos^2
    if sins and coss:
        return Detection("pythagorean-identity", 0.95, "sin^2 and cos^2 together")
    a_sins = {n for n in a.atoms(Pow) if n.base.func is sin and n.exp == 2}
    a_coss = {n for n in a.atoms(Pow) if n.base.func is cos and n.exp == 2}
    if (sins and a_coss and not a_sins) or (coss and a_sins and not a_coss):
        return Detection("pythagorean-identity", 0.9, "swapped sin^2 for cos^2")
    if b.has(sympy.S.One) and (sins or coss) and (a_sins or a_coss):
        return Detection("pythagorean-identity", 0.7, "trig square with a 1")
    return None


def _d_log_power(b, a, x):
    for L in _logs_in(b):
        arg = L.args[0]
        if isinstance(arg, Pow) and not arg.exp.free_symbols:
            return Detection("log-power-rule", 0.92, "exponent inside a log")
        if isinstance(arg, Pow) and arg.exp.free_symbols:
            return Detection("log-power-rule", 0.85, "variable exponent inside a log")
    # after has  p*log(...)  where before had a single log
    if len(_logs_in(b)) == 1 and isinstance(a, Mul):
        if any(isinstance(t, log) for t in a.args) and len(_logs_in(a)) == 1:
            return Detection("log-power-rule", 0.75, "exponent came down in front")
    return None


def _d_log_product_quotient(b, a, x):
    for L in _logs_in(b):
        arg = L.args[0]
        # check division FIRST: a/b is stored as a * b^-1, so it also looks
        # like a multiplication if you don't look for the negative power.
        if _is_fraction(arg):
            return Detection("log-quotient-rule", 0.9, "division inside a log")
        if isinstance(arg, Mul) and len(arg.args) >= 2:
            return Detection("log-product-rule", 0.9, "multiplication inside a log")
    # combining direction: two logs before, one after
    if len(_logs_in(b)) >= 2 and len(_logs_in(a)) == 1:
        if isinstance(b, Add):
            neg = any(t.could_extract_minus_sign() for t in b.args)
            cid = "log-quotient-rule" if neg else "log-product-rule"
            return Detection(cid, 0.8, "two logs combined into one")
    return None


def _d_solving_exponential(b, a, x):
    if _has_symbolic_exponent(b) and _logs_in(a):
        return Detection("solving-exponential-equations", 0.95,
                         "log applied to reach an exponent")
    if _has_symbolic_exponent(b) and not _logs_in(b):
        base_pows = [n for n in b.atoms(Pow) if n.exp.free_symbols and n.base.is_number]
        if base_pows:
            return Detection("solving-exponential-equations", 0.7,
                             "unknown sitting in an exponent")
    return None


def _d_log_definition(b, a, x):
    if _logs_in(b) and not _logs_in(a) and not _has_symbolic_exponent(b):
        return Detection("log-definition", 0.7, "log rewritten as an exponent")
    if _logs_in(b):
        return Detection("log-definition", 0.4, "a logarithm is involved")
    return None


def _d_difference_of_squares(b, a, x):
    if not isinstance(b, Add) or len(b.args) != 2:
        return None
    pos = [t for t in b.args if not t.could_extract_minus_sign()]
    neg = [-t for t in b.args if t.could_extract_minus_sign()]
    if len(pos) != 1 or len(neg) != 1:
        return None
    if _is_perfect_square(pos[0], x) is not None and _is_perfect_square(neg[0], x) is not None:
        conf = 0.95 if _is_product_of_sums(a) else 0.8
        return Detection("difference-of-squares", conf, "a square minus a square")
    return None


def _d_factoring_quadratic(b, a, x):
    if not isinstance(b, Add) or _degree(b, x) != 2:
        return None
    if not _is_product_of_sums(a):
        return None
    try:
        lead = sympy.Poly(b, x).all_coeffs()[0]
    except Exception:
        return None
    if _count_terms(b) >= 3:
        if lead == 1:
            return Detection("factoring-quadratic-simple", 0.9, "x^2 + bx + c factored")
        return Detection("factoring-by-grouping", 0.75,
                         "quadratic with a leading coefficient")
    return None


def _d_grouping(b, a, x):
    if isinstance(b, Add) and _count_terms(b) == 4 and isinstance(a, Mul):
        return Detection("factoring-by-grouping", 0.9, "four terms factored")
    return None


def _d_gcf(b, a, x):
    if not (isinstance(b, Add) and isinstance(a, Mul)):
        return None
    monomials = [t for t in a.args if not isinstance(t, Add)]
    if monomials and any(isinstance(t, Add) for t in a.args) and not _is_product_of_sums(a):
        return Detection("gcf-factoring", 0.85, "a common factor pulled out front")
    return None


def _d_distributive(b, a, x):
    if isinstance(b, Mul) and any(isinstance(t, Add) for t in b.args):
        if isinstance(a, Add) and _count_terms(a) >= _count_terms(b):
            return Detection("distributive-property", 0.9, "parentheses multiplied out")
        return Detection("distributive-property", 0.6, "a product containing a sum")
    if isinstance(b, Pow) and isinstance(b.base, Add) and b.exp == 2 and isinstance(a, Add):
        return Detection("distributive-property", 0.85, "a squared binomial expanded")
    return None


def _d_simplify_rational(b, a, x):
    if _is_fraction(b):
        if not _is_fraction(a):
            return Detection("simplify-rational", 0.9, "a fraction reduced away")
        nb, db = sympy.fraction(sympy.together(b))
        na, da = sympy.fraction(sympy.together(a))
        if db != da:
            return Detection("simplify-rational", 0.85, "common factor cancelled")
        return Detection("simplify-rational", 0.5, "working with a fraction")
    return None


def _d_domain(b, a, x):
    if _is_fraction(b) and (a == sympy.S.Zero or not a.free_symbols):
        return Detection("domain-of-rational", 0.7, "denominator set to zero")
    return None


def _d_absolute_value(b, a, x):
    if b.atoms(Abs):
        return Detection("absolute-value-equations", 0.9, "absolute value present")
    return None


def _d_exponent_rules(b, a, x):
    if isinstance(b, Pow) and isinstance(b.base, Pow):
        return Detection("exponent-rules", 0.9, "a power raised to a power")
    if _same_base_powers(b, x):
        return Detection("exponent-rules", 0.9, "powers of the same base combined")

    # x^7 / x^2  -> same single base top and bottom, nothing else in the way.
    # Contrast with (6x^2)/(3x), which has numeric coefficients and is really
    # a rational-expression simplification, not an exponent rule.
    dens = _neg_powers(b)
    if dens:
        nums = _numer_parts(b)
        if any(p.is_number for p in nums + dens if not p.free_symbols):
            return None                      # coefficients present -> not this
        nb = {_base_symbol(p) for p in nums}
        db = {_base_symbol(p.base) for p in dens}
        nb.discard(None)
        db.discard(None)
        if nb and nb == db:
            # Outranks simplify-rational on purpose: both are technically
            # true for x^7/x^2, but "exponents subtract" is the idea the
            # student is actually reaching for.
            return Detection("exponent-rules", 0.93,
                             "powers divided, so exponents subtract")
    return None


# Order matters: specific patterns get first refusal.
_DETECTORS = [
    _d_pythagorean,
    _d_solving_exponential,
    _d_log_power,
    _d_log_product_quotient,
    _d_absolute_value,
    _d_difference_of_squares,
    _d_grouping,
    _d_factoring_quadratic,
    _d_exponent_rules,
    _d_simplify_rational,
    _d_domain,
    _d_gcf,
    _d_distributive,
    _d_log_definition,
]


def detect_transformation(before, after, top_n: int = 3):
    """Return ranked guesses at which concept the student was applying."""
    x = _free_symbol(before, after)
    found, seen = [], set()
    for fn in _DETECTORS:
        try:
            d = fn(before, after, x)
        except Exception:
            d = None
        if d and d.concept_id not in seen:
            seen.add(d.concept_id)
            found.append(d)
    found.sort(key=lambda d: -d.confidence)
    return found[:top_n]


def detect_in_single(expr, top_n: int = 3):
    """When a student sends ONE expression and says 'I'm stuck here'.

    We look at what ideas are present rather than what changed.
    """
    return detect_transformation(expr, expr, top_n=top_n)
