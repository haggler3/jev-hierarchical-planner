"""L2 - tactical planner: 3D weighted A* over a voxel city, with line-of-sight smoothing.

Cheap and deterministic. It knows nothing about *why* a destination was chosen; it just
finds the best collision-free route to wherever the strategic layer (Jev) points it, and
reports route cost back up so the strategist can reason about it.
"""

from __future__ import annotations

import heapq
import itertools
import math
from typing import List, Optional

import numpy as np

from .world import BOUNDS, CEILING, Building, Zone


class Planner:
    def __init__(self, buildings: List[Building], res: float = 2.0, margin: float = 2.5, vmargin: float = 2.0):
        self.res, self.lo, self.margin = res, BOUNDS[0], margin
        self.n = int(round((BOUNDS[1] - BOUNDS[0]) / res)) + 1
        self.nz = int(CEILING / res) + 1
        xs = self.lo + res * np.arange(self.n)
        zs = res * np.arange(self.nz)
        self.X, self.Y, _ = np.meshgrid(xs, xs, zs, indexing="ij")
        Z = np.meshgrid(xs, xs, zs, indexing="ij")[2]
        occ = np.zeros(self.X.shape, bool)
        for b in buildings:
            occ |= (abs(self.X - b.cx) < b.hx + margin) & (abs(self.Y - b.cy) < b.hy + margin) & (Z < b.h + vmargin)
        occ[:, :, 0] = True
        self.static = occ
        self.version = 0
        self.expanded = 0
        self.offsets = [(dx, dy, dz) for dx, dy, dz in itertools.product((-1, 0, 1), repeat=3) if (dx, dy, dz) != (0, 0, 0)]
        self.step_cost = [res * math.sqrt(dx * dx + dy * dy + (1.6 * dz) ** 2) for dx, dy, dz in self.offsets]
        self.set_zones([])

    def set_zones(self, zones: List[Zone]):
        occ = self.static.copy()
        for z in zones:
            if z.active:
                occ |= (self.X - z.cx) ** 2 + (self.Y - z.cy) ** 2 < (z.r + self.margin) ** 2
        near = occ.copy()
        for ax in range(3):
            for sh in (1, -1):
                near |= np.roll(occ, sh, axis=ax)
        self.occ = occ
        self.occ_b = bytearray(occ.ravel().astype(np.uint8))
        self.near_b = bytearray((near & ~occ).ravel().astype(np.uint8))
        self.version += 1

    # ---- indexing ----
    def _cell(self, p):
        i = int(round((p[0] - self.lo) / self.res)); j = int(round((p[1] - self.lo) / self.res))
        k = int(round(p[2] / self.res))
        return (min(max(i, 0), self.n - 1), min(max(j, 0), self.n - 1), min(max(k, 1), self.nz - 1))

    def _flat(self, c):
        return (c[0] * self.n + c[1]) * self.nz + c[2]

    def _free(self, c):
        return not self.occ_b[self._flat(c)]

    def _snap(self, p, radius):
        c = self._cell(p)
        if self._free(c):
            return c
        best, bd = None, 1e9
        for di in range(-radius, radius + 1):
            for dj in range(-radius, radius + 1):
                for dk in range(-radius, radius + 1):
                    q = (c[0] + di, c[1] + dj, c[2] + dk)
                    if 0 <= q[0] < self.n and 0 <= q[1] < self.n and 1 <= q[2] < self.nz and self._free(q):
                        d = di * di + dj * dj + dk * dk
                        if d < bd:
                            best, bd = q, d
        return best

    def _world(self, c):
        return np.array([self.lo + c[0] * self.res, self.lo + c[1] * self.res, c[2] * self.res])

    def segment_free(self, a, b, step=0.6):
        d = np.linalg.norm(b - a)
        n = max(2, int(d / step) + 1)
        for t in np.linspace(0.0, 1.0, n):
            if self.occ_b[self._flat(self._cell(a + t * (b - a)))]:
                return False
        return True

    def path_blocked(self, path: np.ndarray, from_idx: int = 0) -> bool:
        for i in range(from_idx, len(path) - 1):
            if not self.segment_free(path[i], path[i + 1]):
                return True
        return False

    # ---- planning ----
    def plan(self, start, goal) -> Optional[np.ndarray]:
        s = self._snap(start, 6)
        g = self._snap(goal, 2)
        if s is None or g is None:
            return None
        gw = self._world(g)
        n, nz = self.n, self.nz
        inf = float("inf")
        gscore = {self._flat(s): 0.0}
        parent = {}
        heap = [(0.0, self._flat(s), s)]
        closed = set()
        expanded = 0

        def h(c):
            return 1.25 * self.res * math.sqrt((c[0] - g[0]) ** 2 + (c[1] - g[1]) ** 2 + (1.6 * (c[2] - g[2])) ** 2)

        gf = self._flat(g)
        found = False
        while heap:
            _, f, c = heapq.heappop(heap)
            if f in closed:
                continue
            closed.add(f)
            expanded += 1
            if f == gf:
                found = True
                break
            gc = gscore[f]
            for (dx, dy, dz), sc in zip(self.offsets, self.step_cost):
                q = (c[0] + dx, c[1] + dy, c[2] + dz)
                if not (0 <= q[0] < n and 0 <= q[1] < n and 1 <= q[2] < nz):
                    continue
                qf = (q[0] * n + q[1]) * nz + q[2]
                if self.occ_b[qf] or qf in closed:
                    continue
                ng = gc + sc + (self.res * 0.7 if self.near_b[qf] else 0.0)
                if ng < gscore.get(qf, inf):
                    gscore[qf] = ng
                    parent[qf] = (f, c)
                    heapq.heappush(heap, (ng + h(q), qf, q))
        self.expanded = expanded
        if not found:
            return None
        cells, cur = [g], gf
        while cur in parent:
            cur, c = parent[cur]
            cells.append(c)
        cells.reverse()
        pts = [self._world(c) for c in cells]
        pts[0] = np.array(start, float) if self.segment_free(np.array(start, float), pts[1] if len(pts) > 1 else pts[0]) else pts[0]
        pts[-1] = np.array([goal[0], goal[1], max(goal[2], gw[2] if self._free(g) else goal[2])])
        # string-pulling: keep only the waypoints needed for collision-free straight legs
        out, i = [pts[0]], 0
        while i < len(pts) - 1:
            j = len(pts) - 1
            while j > i + 1 and not self.segment_free(pts[i], pts[j]):
                j -= 1
            out.append(pts[j])
            i = j
        return np.array(out)


def path_length(path: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(path, axis=0), axis=1))) if path is not None and len(path) > 1 else 0.0


class PathFollower:
    """Projects the drone onto the path and returns a lookahead carrot point."""

    def __init__(self, path: np.ndarray):
        self.p = path
        self.seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
        self.cum = np.concatenate([[0.0], np.cumsum(self.seg)])
        self.total = float(self.cum[-1])
        self.idx = 0

    def progress(self, pos) -> float:
        best, bs = 1e9, self.cum[self.idx]
        for i in range(self.idx, min(self.idx + 3, len(self.p) - 1)):
            a, b = self.p[i], self.p[i + 1]
            ab = b - a
            L2 = float(ab @ ab)
            t = 0.0 if L2 < 1e-9 else float(np.clip((pos - a) @ ab / L2, 0, 1))
            d = float(np.linalg.norm(pos - (a + t * ab)))
            if d < best:
                best, bs = d, self.cum[i] + t * self.seg[i]
        while self.idx < len(self.seg) - 1 and bs >= self.cum[self.idx + 1] - 1e-6:
            self.idx += 1
        return bs

    def point_at(self, s: float) -> np.ndarray:
        s = float(np.clip(s, 0.0, self.total))
        i = int(np.clip(np.searchsorted(self.cum, s, side="right") - 1, 0, len(self.seg) - 1))
        t = 0.0 if self.seg[i] < 1e-9 else (s - self.cum[i]) / self.seg[i]
        return self.p[i] + t * (self.p[i + 1] - self.p[i])

    def carrot(self, pos, lookahead):
        s = self.progress(pos)
        return self.point_at(s + lookahead), self.total - s
