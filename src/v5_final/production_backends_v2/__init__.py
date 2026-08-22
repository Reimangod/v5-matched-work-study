"""Six dependency-injected MB5.2 successor entrypoints."""

from .immutable_source import execute as execute_immutable_source
from .magnitude_control import execute as execute_magnitude_control
from .same_structure import execute as execute_same_structure
from .v4_1_one_shot import execute as execute_v4_1_one_shot
from .v5_fixed_whitelist import execute as execute_v5_fixed_whitelist
from .v5_replenishing import execute as execute_v5_replenishing

ENTRYPOINTS_V2 = {
    "immutable-ceo-star-source": execute_immutable_source,
    "same-structure-reoptimization": execute_same_structure,
    "structural-magnitude-pruning": execute_magnitude_control,
    "v4.1-one-shot-joint-compression": execute_v4_1_one_shot,
    "v5-fixed-source-whitelist-no-replenishment": execute_v5_fixed_whitelist,
    "v5-sequential-with-rebuilding": execute_v5_replenishing,
}

__all__ = ["ENTRYPOINTS_V2"]
