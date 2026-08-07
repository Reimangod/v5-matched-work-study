"""Import-only probe executed by the pinned parent Python environment."""

from __future__ import annotations

import json

from .production_kernel_bindings import inspect_pinned_api


def main() -> None:
    print(json.dumps(inspect_pinned_api(), sort_keys=True))


if __name__ == "__main__":
    main()
