"""A small BDD package and a minimal sum-of-products cover (Minato-Morreale ISOP).

Used by the GAL target to turn the gate netlist into the two-level equations a
GAL's AND/OR array holds. Functions are node numbers in a Bdd manager; 0 and 1
are the constants. Variables are numbered in creation order, which is also the
BDD order.

    b = Bdd()
    a, c = b.var("a"), b.var("c")
    f = b.or_(b.and_(a, c), b.not_(a))
    b.isop(f)          # -> [{0: 0}, {1: 1}]  (~a | c)
"""
from __future__ import annotations

from typing import Dict, List, Tuple

Cube = Dict[int, int]          # variable index -> 0 or 1


class Bdd:
    def __init__(self):
        self.nodes: List[Tuple[int, int, int]] = [(1 << 30, 0, 0), (1 << 30, 1, 1)]
        self.unique: Dict[Tuple[int, int, int], int] = {}
        self.names: List[str] = []
        self._ite: Dict[Tuple[int, int, int], int] = {}
        self._isop: Dict[Tuple[int, int], Tuple[List[Cube], int]] = {}

    # ---- construction ----------------------------------------------------------
    def var(self, name: str) -> int:
        self.names.append(name)
        return self._mk(len(self.names) - 1, 0, 1)

    def var_node(self, index: int) -> int:
        return self._mk(index, 0, 1)

    def _mk(self, v: int, lo: int, hi: int) -> int:
        if lo == hi:
            return lo
        key = (v, lo, hi)
        n = self.unique.get(key)
        if n is None:
            n = len(self.nodes)
            self.nodes.append(key)
            self.unique[key] = n
        return n

    def top(self, f: int) -> int:
        return self.nodes[f][0]

    def cof(self, f: int, v: int) -> Tuple[int, int]:
        fv, lo, hi = self.nodes[f]
        return (lo, hi) if fv == v else (f, f)

    def ite(self, f: int, g: int, h: int) -> int:
        if f == 1:
            return g
        if f == 0:
            return h
        if g == h:
            return g
        if g == 1 and h == 0:
            return f
        key = (f, g, h)
        r = self._ite.get(key)
        if r is not None:
            return r
        v = min(self.top(f), self.top(g), self.top(h))
        f0, f1 = self.cof(f, v)
        g0, g1 = self.cof(g, v)
        h0, h1 = self.cof(h, v)
        r = self._mk(v, self.ite(f0, g0, h0), self.ite(f1, g1, h1))
        self._ite[key] = r
        return r

    def not_(self, f: int) -> int:
        return self.ite(f, 0, 1)

    def and_(self, f: int, g: int) -> int:
        return self.ite(f, g, 0)

    def or_(self, f: int, g: int) -> int:
        return self.ite(f, 1, g)

    def xor(self, f: int, g: int) -> int:
        return self.ite(f, self.not_(g), g)

    def mux(self, a: int, b: int, s: int) -> int:     # s ? b : a
        return self.ite(s, b, a)

    def cube(self, c: Cube) -> int:
        f = 1
        for v, val in sorted(c.items(), reverse=True):
            x = self.var_node(v)
            f = self.and_(f, x if val else self.not_(x))
        return f

    # ---- questions ---------------------------------------------------------------
    def support(self, f: int) -> List[int]:
        seen, out, todo = set(), set(), [f]
        while todo:
            n = todo.pop()
            if n < 2 or n in seen:
                continue
            seen.add(n)
            v, lo, hi = self.nodes[n]
            out.add(v)
            todo += [lo, hi]
        return sorted(out)

    def eval(self, f: int, values: Dict[int, int]) -> int:
        while f > 1:
            v, lo, hi = self.nodes[f]
            f = hi if values.get(v, 0) else lo
        return f

    def as_literal(self, f: int):
        """(var, polarity) if f is a single variable or its complement."""
        if f < 2:
            return None
        v, lo, hi = self.nodes[f]
        if (lo, hi) == (0, 1):
            return v, 1
        if (lo, hi) == (1, 0):
            return v, 0
        return None

    # ---- minimal cover -----------------------------------------------------------
    def isop(self, lower: int, upper: int = -1) -> List[Cube]:
        """Irredundant sum of products for any function between `lower` and
        `upper` (lower <= upper; upper defaults to lower: no don't-cares)."""
        if upper < 0:
            upper = lower
        return [dict(c) for c in self._isop_rec(lower, upper)[0]]

    def _isop_rec(self, L: int, U: int) -> Tuple[List[Cube], int]:
        if L == 0:
            return [], 0
        if U == 1:
            return [{}], 1
        key = (L, U)
        r = self._isop.get(key)
        if r is not None:
            return r
        v = min(self.top(L), self.top(U))
        L0, L1 = self.cof(L, v)
        U0, U1 = self.cof(U, v)
        c0, f0 = self._isop_rec(self.and_(L0, self.not_(U1)), U0)
        c1, f1 = self._isop_rec(self.and_(L1, self.not_(U0)), U1)
        Ln = self.or_(self.and_(L0, self.not_(f0)), self.and_(L1, self.not_(f1)))
        cs, fs = self._isop_rec(Ln, self.and_(U0, U1))
        x = self.var_node(v)
        f = self.or_(self.or_(self.and_(self.not_(x), f0), self.and_(x, f1)), fs)
        cubes = [{**c, v: 0} for c in c0] + [{**c, v: 1} for c in c1] + cs
        r = (cubes, f)
        self._isop[key] = r
        return r
