"""Print pinned MB5.2 API identities without constructing a molecule."""

from __future__ import annotations

import json

from .production_kernel_bindings_v2 import inspect_pinned_api_v2


def main() -> None:
    print(json.dumps(inspect_pinned_api_v2(), sort_keys=True))


if __name__ == "__main__":
    main()
