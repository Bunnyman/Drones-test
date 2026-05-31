#!/usr/bin/env python3
"""Pixel -> geographic (lon/lat) georeferencing.

Two projection modes:

* ``affine`` (default): lon = a*x + b*y + c, lat = d*x + e*y + f, fitted by
  least squares. Good for small areas when control points are read precisely.
* ``mercator``: north-up Web Mercator. Longitude is linear in x and latitude is
  linear in y *through the Mercator term*, so the two axes are fit
  independently. This is the right model for a north-up slippy-map screenshot
  and is most accurate when calibrated from the map's own graticule.

Pure standard library — no numpy required.
"""

import json
import math


def _mercy(lat_deg):
    return math.log(math.tan(math.pi / 4 + math.radians(lat_deg) / 2))


def _inv_mercy(m):
    return math.degrees(2 * math.atan(math.exp(m)) - math.pi / 2)


class Georeferencer:
    def __init__(self, control_points, projection="affine"):
        """control_points: list of dicts like
        {"name": "Izium", "pixel": [x, y], "lonlat": [lon, lat]}
        At least 3 non-collinear points are required (2 for mercator).
        """
        self.control_points = control_points
        self.projection = projection
        if projection == "mercator":
            self._fit_mercator(control_points)
        else:
            if len(control_points) < 3:
                raise ValueError("need at least 3 control points for an affine fit")
            self.lon_params, self.lat_params = self._fit(control_points)

    # --- linear algebra helpers (Gaussian elimination, partial pivoting) ---
    @staticmethod
    def _gauss(matrix, rhs):
        n = len(rhs)
        aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
        for i in range(n):
            piv_row = max(range(i, n), key=lambda r: abs(aug[r][i]))
            aug[i], aug[piv_row] = aug[piv_row], aug[i]
            pivot = aug[i][i]
            if abs(pivot) < 1e-12:
                raise ValueError("singular control-point configuration")
            for j in range(i, n + 1):
                aug[i][j] /= pivot
            for r in range(n):
                if r != i:
                    factor = aug[r][i]
                    for j in range(i, n + 1):
                        aug[r][j] -= factor * aug[i][j]
        return [aug[i][n] for i in range(n)]

    @staticmethod
    def _linfit(xs, ys):
        """Least-squares y = m*x + b."""
        n = len(xs)
        sx, sy = sum(xs), sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))
        denom = n * sxx - sx * sx
        if abs(denom) < 1e-12:
            raise ValueError("degenerate control points for linear fit")
        m = (n * sxy - sx * sy) / denom
        b = (sy - m * sx) / n
        return m, b

    def _fit(self, pts):
        xs = [p["pixel"][0] for p in pts]
        ys = [p["pixel"][1] for p in pts]

        def solve(values):
            sxx = sum(x * x for x in xs)
            sxy = sum(x * y for x, y in zip(xs, ys))
            sx = sum(xs)
            syy = sum(y * y for y in ys)
            sy = sum(ys)
            s = float(len(xs))
            bx = sum(x * v for x, v in zip(xs, values))
            by = sum(y * v for y, v in zip(ys, values))
            bc = sum(values)
            normal = [[sxx, sxy, sx], [sxy, syy, sy], [sx, sy, s]]
            return self._gauss(normal, [bx, by, bc])

        lon_v = [p["lonlat"][0] for p in pts]
        lat_v = [p["lonlat"][1] for p in pts]
        return solve(lon_v), solve(lat_v)

    def _fit_mercator(self, pts):
        if len(pts) < 2:
            raise ValueError("need at least 2 control points for a mercator fit")
        xs = [p["pixel"][0] for p in pts]
        ys = [p["pixel"][1] for p in pts]
        lons = [p["lonlat"][0] for p in pts]
        mys = [_mercy(p["lonlat"][1]) for p in pts]
        # lon = A*x + B  ;  mercY = C*y + D
        self._A, self._B = self._linfit(xs, lons)
        self._C, self._D = self._linfit(ys, mys)

    def to_lonlat(self, x, y):
        if self.projection == "mercator":
            lon = self._A * x + self._B
            lat = _inv_mercy(self._C * y + self._D)
            return lon, lat
        a, b, c = self.lon_params
        d, e, f = self.lat_params
        return a * x + b * y + c, d * x + e * y + f

    def residuals_m(self):
        """Return list of (name, error_metres) for each control point."""
        out = []
        for p in self.control_points:
            px, py = p["pixel"]
            lon, lat = p["lonlat"]
            plon, plat = self.to_lonlat(px, py)
            dlat = (plat - lat) * 111320.0
            dlon = (plon - lon) * 111320.0 * math.cos(math.radians(lat))
            out.append((p.get("name", "?"), math.hypot(dlat, dlon)))
        return out

    @classmethod
    def from_file(cls, path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return cls(data["control_points"],
                   projection=data.get("projection", "affine"))
