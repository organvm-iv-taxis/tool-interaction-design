"""Inject conductor capabilities into the standalone router.

Import this module after importing router to wire up contract validation,
plugin loading, policy resolution, and schema validation. This preserves
the layer invariant: router never imports conductor; conductor extends router.
"""

from __future__ import annotations


def install() -> None:
    """Patch router module-level hooks with real conductor implementations."""
    import router as _router

    from .contracts import assert_contract
    from .plugins import load_plugin_clusters
    from .policy import load_policy
    from .schemas import validate_document

    _router.inject_extensions(
        contract_fn=assert_contract,
        plugin_fn=load_plugin_clusters,
        policy_fn=load_policy,
        schema_fn=validate_document,
    )
