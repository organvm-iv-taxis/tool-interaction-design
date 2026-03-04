"""conductor — The AI-Conductor's Operating System."""

__version__ = "0.5.0"

from .constants import (
    BASE,
    CONFIG_FILE,
    EXPORTS_DIR,
    GENERATED_DIR,
    GOVERNANCE_PATH,
    MAX_CANDIDATE_PER_ORGAN,
    MAX_PUBLIC_PROCESS_PER_ORGAN,
    ONTOLOGY_PATH,
    ORGANS,
    PHASE_CLUSTERS,
    PHASE_ROLES,
    PHASES,
    PROMOTION_STATES,
    PROMOTION_TRANSITIONS,
    REGISTRY_PATH,
    ROUTING_PATH,
    SESSIONS_DIR,
    SESSION_STATE_FILE,
    STATS_FILE,
    TEMPLATES_DIR,
    VALID_TRANSITIONS,
    ConductorError,
    GovernanceError,
    SessionError,
    atomic_write,
    get_phase_clusters,
    load_config,
    organ_short,
    resolve_organ_key,
)
from .governance import GovernanceRuntime
from .patchbay import Patchbay
from .product import ProductExtractor
from .session import Session, SessionEngine
from .workqueue import WorkItem, WorkQueue

__all__ = [
    "__version__",
    # Constants
    "BASE",
    "CONFIG_FILE",
    "EXPORTS_DIR",
    "GENERATED_DIR",
    "GOVERNANCE_PATH",
    "MAX_CANDIDATE_PER_ORGAN",
    "MAX_PUBLIC_PROCESS_PER_ORGAN",
    "ONTOLOGY_PATH",
    "ORGANS",
    "PHASE_CLUSTERS",
    "PHASE_ROLES",
    "PHASES",
    "PROMOTION_STATES",
    "PROMOTION_TRANSITIONS",
    "REGISTRY_PATH",
    "ROUTING_PATH",
    "SESSIONS_DIR",
    "SESSION_STATE_FILE",
    "STATS_FILE",
    "TEMPLATES_DIR",
    "VALID_TRANSITIONS",
    # Exceptions
    "ConductorError",
    "GovernanceError",
    "SessionError",
    # Helpers
    "atomic_write",
    "get_phase_clusters",
    "load_config",
    "organ_short",
    "resolve_organ_key",
    # Classes
    "GovernanceRuntime",
    "Patchbay",
    "ProductExtractor",
    "Session",
    "SessionEngine",
    "WorkItem",
    "WorkQueue",
]
