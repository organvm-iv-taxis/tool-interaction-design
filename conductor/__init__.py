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
from .doctor import run_doctor
from .executor import WorkflowExecutor
from .governance import GovernanceRuntime
from .handoff import create_handoff_envelope, edge_health_report, get_trace_bundle, simulate_route_handoff, validate_handoff_payload
from .integrity import IntegrityIssue, IntegrityReport, run_integrity_checks
from .migrate import migrate_governance, migrate_registry
from .observability import log_event
from .patchbay import Patchbay
from .policy import Policy, load_policy
from .product import ProductExtractor
from .schemas import SchemaIssue, assert_valid_document, load_schema, validate_document
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
    "load_policy",
    "Policy",
    "organ_short",
    "resolve_organ_key",
    # Classes
    "GovernanceRuntime",
    "create_handoff_envelope",
    "simulate_route_handoff",
    "validate_handoff_payload",
    "edge_health_report",
    "get_trace_bundle",
    "Patchbay",
    "ProductExtractor",
    "Session",
    "SessionEngine",
    "WorkItem",
    "WorkQueue",
    # Validation and observability
    "SchemaIssue",
    "load_schema",
    "validate_document",
    "assert_valid_document",
    "run_integrity_checks",
    "IntegrityIssue",
    "IntegrityReport",
    "run_doctor",
    "WorkflowExecutor",
    "migrate_registry",
    "migrate_governance",
    "log_event",
]
