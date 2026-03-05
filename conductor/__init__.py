"""conductor — The AI-Conductor's Operating System.

Public API only. Internal constants, paths, and helpers are available
via their respective submodules (e.g., `conductor.constants`).
"""

__version__ = "0.5.1"

# Exceptions
from .constants import ConductorError, GovernanceError, SessionError

# Core runtime
from .session import Session, SessionEngine
from .governance import GovernanceRuntime
from .patchbay import Patchbay
from .executor import WorkflowExecutor
from .workqueue import WorkItem, WorkQueue

# Oracle
from .oracle import Advisory, DETECTOR_REGISTRY, Oracle, OracleContext, OracleProfile

# Guardian Angel
from .guardian import GuardianAngel
from .wisdom import WisdomCorpus, WisdomEntry

# Handoff / routing
from .handoff import (
    create_handoff_envelope,
    edge_health_report,
    get_trace_bundle,
    simulate_route_handoff,
    validate_handoff_payload,
)

# Policy
from .policy import Policy, load_policy

# Observability
from .observability import log_event

__all__ = [
    "__version__",
    # Exceptions
    "ConductorError",
    "GovernanceError",
    "SessionError",
    # Core runtime
    "Session",
    "SessionEngine",
    "GovernanceRuntime",
    "Patchbay",
    "WorkflowExecutor",
    "WorkItem",
    "WorkQueue",
    # Oracle
    "Advisory",
    "DETECTOR_REGISTRY",
    "Oracle",
    "OracleContext",
    "OracleProfile",
    # Guardian Angel
    "GuardianAngel",
    "WisdomCorpus",
    "WisdomEntry",
    # Handoff / routing
    "create_handoff_envelope",
    "edge_health_report",
    "get_trace_bundle",
    "simulate_route_handoff",
    "validate_handoff_payload",
    # Policy
    "Policy",
    "load_policy",
    # Observability
    "log_event",
]
