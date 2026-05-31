"""Print the residual error of the current calibration.json control points.

    python -m drone_watch.calibrate_check [path/to/calibration.json]
"""

import os
import sys

from .georef import Georeferencer


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    path = argv[0] if argv else os.path.join(
        os.path.dirname(__file__), "calibration.json")
    geo = Georeferencer.from_file(path)
    print(f"calibration: {path}")
    worst = 0.0
    for name, err in geo.residuals_m():
        worst = max(worst, err)
        print(f"  {name:22s} residual ~ {err:7.0f} m")
    print(f"  --> max residual ~ {worst:.0f} m")
    if worst > 1000:
        print("  WARNING: residuals > 1 km. Re-read your control-point "
              "pixels and coordinates for better accuracy.")


if __name__ == "__main__":
    main()
