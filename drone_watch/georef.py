"""Pixel -> geographic (lon/lat) georeferencing via a least-squares affine fit.

The map source renders a near-linear projection over this small area, so an
affine transform (lon = a*x + b*y + c, lat = d*x + e*y + f) fitted from a few
control points is accurate to within a few hundred metres *if the control
points are read precisely and the map extent/zoom is fixed*.

Pure standard library — no numpy required.
"""

import json
import math


class Georeferencer:
    def __init__(self, control_points):
        """control_points: list of dicts like
        {"name": "Izium", "pixel": [x, y], "lonlat": [lon, lat]}
        At least 3 non-collinear points are required.
        """
        self.control_points = control_points
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

    def to_lonlat(self, x, y):
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
        return cls(data["control_points"])
