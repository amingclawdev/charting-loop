"""Benchmark-facing agents and prompt contracts for Charting Loop studies.

The package deliberately avoids importing Harbor at module import time.  This keeps
the prompt/contract helpers usable in the repository's dependency-free test suite;
Harbor imports :mod:`benchmark_agents.harbor_agent` only for an actual benchmark run.
"""

from .contract import (
    ASSESSMENT_SCHEMA,
    CLOSURE_PATH,
    CORRIDOR_PATH,
    FREEZE_PATH,
    QA_PATH,
    RUNTIME_ROOT,
    builder_prompt,
    closure_prompt,
    freeze_program,
    qa_prompt,
    repair_prompt,
    validate_qa_assessment,
    worker_prompt,
)

__all__ = [
    "ASSESSMENT_SCHEMA",
    "CLOSURE_PATH",
    "CORRIDOR_PATH",
    "FREEZE_PATH",
    "QA_PATH",
    "RUNTIME_ROOT",
    "builder_prompt",
    "closure_prompt",
    "freeze_program",
    "qa_prompt",
    "repair_prompt",
    "validate_qa_assessment",
    "worker_prompt",
]
