from __future__ import annotations

import json
from pathlib import Path

from app.main import app


def main() -> None:
    dest = Path(__file__).resolve().parents[2] / "openapi.json"
    dest.write_text(json.dumps(app.openapi(), indent=2))
    print(dest)


if __name__ == "__main__":
    main()
