"""Immutable, task-neutral indexes for Corridor graph inspection.

The index is an advisory view over an already validated graph.  It never admits
Facts, ratifies Rules, authorizes mutation, or turns a diagnostic into a Gate.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from .compiler import (
    project_witness_obligation_templates,
    semantic_edge_id,
)
from .core import CorridorKitError, sha256_json


HARD_RELATIONSHIPS = frozenset(
    {"requires", "precondition_for", "produces_fact_for", "precedes"}
)
NON_TOPOLOGICAL_RELATIONSHIPS = frozenset(
    {
        "derived_from",
        "subsumes",
        "overlaps",
        "can_parallelize_with",
        "conflicts",
        "invalidates",
    }
)
ACTIVE_CONTEXT_DEFAULT_MAX_CHARS = 24_000


def canonical_dependency_edge(
    *, edge_id: str, relationship: str, from_ref: str, to_ref: str, source: str
) -> dict[str, str | bool]:
    """Normalize one declared relationship to dependant/prerequisite orientation."""

    if relationship == "requires":
        dependant, prerequisite = from_ref, to_ref
    elif relationship in {"precondition_for", "produces_fact_for", "precedes"}:
        dependant, prerequisite = to_ref, from_ref
    else:
        dependant, prerequisite = from_ref, to_ref
    return {
        "edge_id": edge_id,
        "relationship": relationship,
        "from_ref": from_ref,
        "to_ref": to_ref,
        "dependant_ref": dependant,
        "prerequisite_ref": prerequisite,
        "topological": relationship in HARD_RELATIONSHIPS,
        "source": source,
    }


def _stable_closure(start: str, adjacency: Mapping[str, set[str]]) -> list[str]:
    seen: set[str] = set()
    pending = list(reversed(sorted(adjacency.get(start, set()))))
    while pending:
        node = pending.pop()
        if node in seen:
            continue
        seen.add(node)
        pending.extend(
            reversed(sorted(adjacency.get(node, set()) - seen))
        )
    return sorted(seen)


def _topological_order(nodes: Iterable[str], dependencies: Mapping[str, set[str]]) -> list[str]:
    remaining = {node: set(dependencies.get(node, set())) for node in set(nodes)}
    order: list[str] = []
    while remaining:
        ready = sorted(node for node, refs in remaining.items() if not refs)
        if not ready:
            raise CorridorKitError("hard dependency graph contains a cycle")
        order.extend(ready)
        for node in ready:
            remaining.pop(node)
        for refs in remaining.values():
            refs.difference_update(ready)
    return order


def _copy(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _copy(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_copy(child) for child in value]
    if isinstance(value, list):
        return [_copy(child) for child in value]
    if isinstance(value, frozenset):
        return sorted(value)
    return value


@dataclass(frozen=True)
class GraphIndex:
    """Digest-bound immutable query surface for one validated graph."""

    graph_digest: str
    graph_bytes_digest: str
    head_record_id: str | None
    _nodes: Mapping[str, Mapping[str, Any]]
    _edges: tuple[Mapping[str, Any], ...]
    _semantic_edges: Mapping[str, Mapping[str, Any]]
    _witness_obligations: Mapping[str, Mapping[str, Any]]
    _dependencies: Mapping[str, frozenset[str]]
    _dependants: Mapping[str, frozenset[str]]
    _conflicts: Mapping[str, frozenset[str]]
    _invalidates: Mapping[str, frozenset[str]]
    _historical_dependants: Mapping[str, frozenset[str]]
    _topology_nodes: frozenset[str]
    _projection: Mapping[str, Any]
    _rule_history: Mapping[str, tuple[Mapping[str, Any], ...]]
    _rule_closure_history: Mapping[str, tuple[Mapping[str, Any], ...]]

    @classmethod
    def build(
        cls,
        *,
        projection: Mapping[str, Any],
        records: Sequence[Mapping[str, Any]],
        graph_digest: str,
        graph_bytes_digest: str,
        head_record_id: str | None,
    ) -> "GraphIndex":
        nodes: dict[str, Mapping[str, Any]] = {}

        def add(kind: str, ref: str, body: Mapping[str, Any]) -> None:
            nodes[ref] = MappingProxyType(
                {"ref": ref, "kind": kind, "body": MappingProxyType(dict(body))}
            )

        for ref, body in projection.get("source_artifacts", {}).items():
            add("task_source_artifact", ref, body)
        for ref, body in projection.get("source_clauses", {}).items():
            add("source_clause", ref, body)
        for rule_id, record_id in projection.get("rule_records", {}).items():
            add(
                "rule",
                rule_id,
                {
                    "rule_id": rule_id,
                    "record_id": record_id,
                    "statement": projection.get("rule_statements", {}).get(rule_id, ""),
                    "ratified": rule_id in projection.get("ratified_rules", set()),
                    "rule_closure_digest": projection.get("rule_closures", {}).get(rule_id),
                },
            )
        for ref, body in projection.get("checklist_items", {}).items():
            add("acceptance_checklist_item", ref, body)
        for ref, body in projection.get("fact_bodies", {}).items():
            add("fact", ref, body)
        for ref, body in projection.get("positions", {}).items():
            add("position", ref, body)
        for ref, body in projection.get("directions", {}).items():
            add("direction", ref, body)

        edges: list[Mapping[str, Any]] = []
        historical_dependants: dict[str, set[str]] = {}
        ratified_rules = set(projection.get("ratified_rules", set()))
        current_rule_records = projection.get("rule_records", {})
        provenance_digests = projection.get("rule_source_provenance_digests", {})
        for edge_id, body in sorted(projection.get("dependencies", {}).items()):
            source_rule_id = body.get("source_rule_id")
            target_rule_id = body.get("target_rule_id")
            if (
                source_rule_id not in ratified_rules
                or current_rule_records.get(source_rule_id)
                != body.get("source_rule_record_id")
            ):
                continue
            if target_rule_id is not None and (
                target_rule_id not in ratified_rules
                or current_rule_records.get(target_rule_id)
                != body.get("target_rule_record_id")
                or provenance_digests.get(source_rule_id)
                != body.get("source_rule_provenance_digest")
                or provenance_digests.get(target_rule_id)
                != body.get("target_rule_provenance_digest")
            ):
                continue
            edges.append(
                MappingProxyType(
                    canonical_dependency_edge(
                        edge_id=edge_id,
                        relationship=str(body["relationship"]),
                        from_ref=str(body["from_ref"]),
                        to_ref=str(body["to_ref"]),
                        source="typed_dependency",
                    )
                )
            )

        witness_obligations: dict[str, Mapping[str, Any]] = {}
        witness_ids_by_checklist: dict[str, list[str]] = {}
        for rule_id in sorted(ratified_rules):
            semantics = projection.get("rule_semantics", {}).get(rule_id)
            statement = projection.get("rule_statements", {}).get(rule_id)
            if not isinstance(semantics, Mapping) or not isinstance(statement, str):
                continue
            for obligation in project_witness_obligation_templates(
                rule_id=rule_id,
                statement=statement,
                semantics=semantics,
            ):
                checklist_id = str(obligation["checklist_item_id"])
                if checklist_id not in projection.get("checklist_items", {}):
                    continue
                obligation_id = str(obligation["witness_obligation_id"])
                witness_obligations[obligation_id] = MappingProxyType(obligation)
                witness_ids_by_checklist.setdefault(checklist_id, []).append(
                    obligation_id
                )

        slice_details: dict[str, dict[str, Any]] = {}
        for clause_id, clause in projection.get("source_clauses", {}).items():
            for source_slice in clause.get("source_slices", []):
                slice_id = source_slice.get("slice_id")
                if not isinstance(slice_id, str):
                    continue
                slice_details[slice_id] = {
                    "slice_id": slice_id,
                    "clause_id": clause_id,
                    "source_id": source_slice.get("source_id"),
                    "representation": source_slice.get(
                        "representation", "source_bytes"
                    ),
                    "byte_start": source_slice.get("byte_start"),
                    "byte_end": source_slice.get("byte_end"),
                    "slice_digest": source_slice.get("slice_digest"),
                }
        rule_binding_roles = {
            rule_id: {
                item.get("slice_id"): item.get("semantic_role")
                for item in bindings
                if isinstance(item, Mapping)
            }
            for rule_id, bindings in projection.get(
                "rule_source_bindings", {}
            ).items()
        }
        semantic_edges: dict[str, Mapping[str, Any]] = {}
        projected_relationships = {
            "precedes": "precondition_for",
            "requires": "requires",
            "precondition_for": "precondition_for",
            "invalidates": "invalidates",
            "conflicts": "conflicts",
        }
        typed_dependencies = projection.get("dependencies", {})
        for body in projection.get("rule_dependencies", []):
            from_rule_id = body.get("from_rule_id")
            to_rule_id = body.get("to_rule_id")
            relationship = body.get("relationship")
            if (
                from_rule_id not in ratified_rules
                or to_rule_id not in ratified_rules
                or not isinstance(relationship, str)
            ):
                continue
            provenance = body.get("edge_provenance")
            if not isinstance(provenance, Mapping):
                provenance = {
                    "kind": "legacy_unresolved",
                    "source_slice_ids": [],
                    "derivation_kind": None,
                    "input_rule_provenance_digests": {},
                }
            source_slice_ids = [
                value
                for value in provenance.get("source_slice_ids", [])
                if isinstance(value, str)
            ]
            edge_ref = semantic_edge_id(
                from_rule_id=str(from_rule_id),
                to_rule_id=str(to_rule_id),
                declared_relationship=relationship,
            )
            projected_relationship = projected_relationships.get(relationship)
            typed_expansion_ids = sorted(
                dependency_id
                for dependency_id, dependency in typed_dependencies.items()
                if dependency.get("source_rule_id") == from_rule_id
                and dependency.get("target_rule_id") == to_rule_id
                and dependency.get("relationship") == projected_relationship
            )
            endpoint_rules = (str(from_rule_id), str(to_rule_id))
            semantic_edges[edge_ref] = MappingProxyType(
                {
                    "semantic_edge_id": edge_ref,
                    "from_rule_id": from_rule_id,
                    "to_rule_id": to_rule_id,
                    "from_rule_record_id": current_rule_records.get(from_rule_id),
                    "to_rule_record_id": current_rule_records.get(to_rule_id),
                    "declared_relationship": relationship,
                    "relationship_alignment": body.get("relationship_alignment"),
                    "edge_provenance": dict(provenance),
                    "relationship_expectation_status": (
                        "source_bound"
                        if provenance.get("kind") == "direct" and source_slice_ids
                        else "unresolved"
                    ),
                    "relationship_source_bindings": [
                        {
                            **slice_details[slice_id],
                            "semantic_role": rule_binding_roles.get(
                                str(from_rule_id), {}
                            ).get(slice_id),
                        }
                        for slice_id in source_slice_ids
                        if slice_id in slice_details
                    ],
                    "relationship_derivation_inputs": dict(
                        provenance.get("input_rule_provenance_digests", {})
                    ),
                    "endpoint_condition_kinds": {
                        rule_id: sorted(
                            {
                                condition.get("condition_kind", "legacy_untyped")
                                for condition in projection.get("rule_semantics", {})
                                .get(rule_id, {})
                                .get("conditions", [])
                            }
                        )
                        for rule_id in endpoint_rules
                    },
                    "endpoint_checklist_item_ids": {
                        rule_id: sorted(
                            item_id
                            for item_id, item in projection.get(
                                "checklist_items", {}
                            ).items()
                            if item.get("source_rule_id") == rule_id
                        )
                        for rule_id in endpoint_rules
                    },
                    "endpoint_witness_obligation_ids": {
                        rule_id: sorted(
                            obligation_id
                            for obligation_id, obligation in witness_obligations.items()
                            if obligation.get("rule_id") == rule_id
                        )
                        for rule_id in endpoint_rules
                    },
                    "typed_expansion_ids": typed_expansion_ids,
                }
            )
        for index, body in enumerate(projection.get("rule_dependencies", []), start=1):
            historical_edge = canonical_dependency_edge(
                edge_id=str(body.get("dependency_id") or f"rule-dependency:{index}"),
                relationship=str(body["relationship"]),
                from_ref=str(body["from_rule_id"]),
                to_ref=str(body["to_rule_id"]),
                source="rule_dependency",
            )
            if historical_edge["topological"]:
                historical_dependants.setdefault(
                    str(historical_edge["prerequisite_ref"]), set()
                ).add(str(historical_edge["dependant_ref"]))
            if (
                body.get("from_rule_id") not in ratified_rules
                or body.get("to_rule_id") not in ratified_rules
            ):
                continue
            source_rule_id = str(body["from_rule_id"])
            target_rule_id = str(body["to_rule_id"])
            source_provenance = provenance_digests.get(source_rule_id)
            target_provenance = provenance_digests.get(target_rule_id)
            if source_provenance is not None:
                if (
                    body.get("source_rule_provenance_digest") != source_provenance
                    or body.get("target_rule_provenance_digest") != target_provenance
                ):
                    continue
                expected_dependency = next(
                    (
                        item
                        for item in projection.get("rule_semantics", {})
                        .get(source_rule_id, {})
                        .get("dependencies", [])
                        if item.get("relationship") == body.get("relationship")
                        and item.get("target_rule_id") == target_rule_id
                    ),
                    None,
                )
                if (
                    expected_dependency is None
                    or body.get("edge_provenance")
                    != expected_dependency.get("provenance")
                    or (
                        "alignment" in expected_dependency
                        and body.get("relationship_alignment")
                        != expected_dependency.get("alignment")
                    )
                ):
                    continue
            edge_id = str(body.get("dependency_id") or f"rule-dependency:{index}")
            edges.append(
                MappingProxyType(
                    canonical_dependency_edge(
                        edge_id=edge_id,
                        relationship=str(body["relationship"]),
                        from_ref=str(body["from_rule_id"]),
                        to_ref=str(body["to_rule_id"]),
                        source="rule_dependency",
                    )
                )
            )

        topology_nodes = set(projection.get("checklist_items", {}))
        topology_nodes.update(ratified_rules)
        topology_nodes.update(projection.get("fact_ids", set()))
        dependencies: dict[str, set[str]] = {ref: set() for ref in topology_nodes}
        dependants: dict[str, set[str]] = {ref: set() for ref in topology_nodes}
        conflicts: dict[str, set[str]] = {ref: set() for ref in topology_nodes}
        invalidates: dict[str, set[str]] = {ref: set() for ref in topology_nodes}
        for edge in edges:
            source = str(edge["from_ref"])
            target = str(edge["to_ref"])
            dependencies.setdefault(source, set())
            dependencies.setdefault(target, set())
            dependants.setdefault(source, set())
            dependants.setdefault(target, set())
            conflicts.setdefault(source, set())
            conflicts.setdefault(target, set())
            invalidates.setdefault(source, set())
            invalidates.setdefault(target, set())
            if edge["topological"]:
                dependant = str(edge["dependant_ref"])
                prerequisite = str(edge["prerequisite_ref"])
                dependencies.setdefault(dependant, set()).add(prerequisite)
                dependants.setdefault(prerequisite, set()).add(dependant)
            elif edge["relationship"] == "conflicts":
                conflicts[source].add(target)
                conflicts[target].add(source)
            elif edge["relationship"] == "invalidates":
                invalidates[source].add(target)

        histories: dict[str, list[Mapping[str, Any]]] = {}
        checklist_ids_by_rule_record: dict[str, list[str]] = {}
        for record in records:
            if record.get("record_type") != "acceptance_checklist_item":
                continue
            body = record.get("body", {})
            rule_record_id = body.get("source_rule_record_id")
            checklist_item_id = body.get("checklist_item_id")
            if isinstance(rule_record_id, str) and isinstance(checklist_item_id, str):
                checklist_ids_by_rule_record.setdefault(rule_record_id, []).append(
                    checklist_item_id
                )
        closure_histories: dict[str, list[Mapping[str, Any]]] = {}
        for record in records:
            if record.get("record_type") not in {
                "rule_proposal",
                "rule_revision",
                "rule_ratification",
            }:
                continue
            body = record.get("body", {})
            rule_id = body.get("rule_id")
            if isinstance(rule_id, str):
                histories.setdefault(rule_id, []).append(
                    MappingProxyType(
                        {
                            "record_type": record["record_type"],
                            "record_id": record["record_id"],
                            "sequence": record["sequence"],
                            "rule_closure_digest": body.get("rule_closure_digest"),
                        }
                    )
                )
                if record["record_type"] == "rule_ratification":
                    rule_record_id = body.get("rule_record_id")
                    closure_contents = {
                        "ratification_record_id": record["record_id"],
                        "ratification_body": dict(body),
                        "checklist_item_ids": sorted(
                            checklist_ids_by_rule_record.get(str(rule_record_id), [])
                        ),
                    }
                    closure_histories.setdefault(rule_id, []).append(
                        MappingProxyType(
                            {
                                **closure_contents,
                                "closure_projection_digest": sha256_json(
                                    closure_contents
                                ),
                            }
                        )
                    )

        return cls(
            graph_digest=graph_digest,
            graph_bytes_digest=graph_bytes_digest,
            head_record_id=head_record_id,
            _nodes=MappingProxyType(nodes),
            _edges=tuple(edges),
            _semantic_edges=MappingProxyType(semantic_edges),
            _witness_obligations=MappingProxyType(witness_obligations),
            _dependencies=MappingProxyType(
                {key: frozenset(value) for key, value in dependencies.items()}
            ),
            _dependants=MappingProxyType(
                {key: frozenset(value) for key, value in dependants.items()}
            ),
            _conflicts=MappingProxyType(
                {key: frozenset(value) for key, value in conflicts.items()}
            ),
            _invalidates=MappingProxyType(
                {key: frozenset(value) for key, value in invalidates.items()}
            ),
            _historical_dependants=MappingProxyType(
                {
                    key: frozenset(value)
                    for key, value in historical_dependants.items()
                }
            ),
            _topology_nodes=frozenset(topology_nodes),
            _projection=MappingProxyType(dict(projection)),
            _rule_history=MappingProxyType(
                {key: tuple(value) for key, value in histories.items()}
            ),
            _rule_closure_history=MappingProxyType(
                {key: tuple(value) for key, value in closure_histories.items()}
            ),
        )

    def _envelope(self, **payload: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "advisory_only": True,
            "authorizes_mutation": False,
            "blocking_gate": False,
            "graph_digest": self.graph_digest,
            "graph_bytes_digest": self.graph_bytes_digest,
            "head_record_id": self.head_record_id,
            **payload,
        }

    def node(self, ref: str) -> dict[str, Any]:
        node = self._nodes.get(ref)
        if node is None:
            raise CorridorKitError(f"unknown graph node: {ref}")
        return self._envelope(node=_copy(node))

    def neighbors(self, ref: str) -> dict[str, Any]:
        self.node(ref)
        inbound = [
            _copy(edge)
            for edge in self._edges
            if edge["to_ref"] == ref
        ]
        outbound = [
            _copy(edge)
            for edge in self._edges
            if edge["from_ref"] == ref
        ]
        return self._envelope(ref=ref, inbound=inbound, outbound=outbound)

    def prerequisite_closure(self, ref: str) -> dict[str, Any]:
        return self._envelope(
            ref=ref,
            prerequisite_refs=_stable_closure(ref, self._dependencies),
            relationship_direction="dependant_to_prerequisite",
        )

    def dependant_closure(self, ref: str) -> dict[str, Any]:
        return self._envelope(
            ref=ref,
            dependant_refs=_stable_closure(ref, self._dependants),
            relationship_direction="prerequisite_to_dependant",
        )

    def impact(self, ref: str) -> dict[str, Any]:
        return self._envelope(
            ref=ref,
            dependant_refs=_stable_closure(ref, self._dependants),
            invalidated_refs=_stable_closure(ref, self._invalidates),
            conflict_refs=sorted(self._conflicts.get(ref, frozenset())),
        )

    def topology(self) -> dict[str, Any]:
        return self._envelope(
            topological_order=_topological_order(
                self._topology_nodes,
                {key: set(value) for key, value in self._dependencies.items()},
            ),
            excluded_relationships=sorted(NON_TOPOLOGICAL_RELATIONSHIPS),
        )

    def frontier(self) -> dict[str, Any]:
        positions = self._projection.get("positions", {})
        latest_ref = next(reversed(positions), None)
        latest = positions.get(latest_ref, {}) if latest_ref else {}
        return self._envelope(
            latest_position_ref=latest_ref,
            ready_item_ids=list(latest.get("ready_item_ids", [])),
            blocked_item_ids=list(latest.get("blocked_item_ids", [])),
            unresolved_checklist_item_ids=list(
                latest.get("unresolved_checklist_item_ids", [])
            ),
        )

    def path(self, prerequisite_ref: str, dependant_ref: str) -> dict[str, Any]:
        pending: deque[tuple[str, list[str]]] = deque(
            [(prerequisite_ref, [prerequisite_ref])]
        )
        seen: set[str] = set()
        found: list[str] = []
        while pending:
            node, path = pending.popleft()
            if node == dependant_ref:
                found = path
                break
            if node in seen:
                continue
            seen.add(node)
            for child in sorted(self._dependants.get(node, frozenset())):
                pending.append((child, [*path, child]))
        return self._envelope(
            prerequisite_ref=prerequisite_ref,
            dependant_ref=dependant_ref,
            path=found,
            found=bool(found),
            relationship_direction="prerequisite_to_dependant",
        )

    def source_trace(self, ref: str) -> dict[str, Any]:
        rule_ids: set[str] = set()
        if ref in self._projection.get("rule_records", {}):
            rule_ids.add(ref)
        checklist = self._projection.get("checklist_items", {}).get(ref)
        if checklist:
            rule_ids.add(str(checklist["source_rule_id"]))
        clause_ids = sorted(
            {
                clause_id
                for rule_id in rule_ids
                for clause_id in self._projection.get("rule_source_clause_ids", {}).get(
                    rule_id, []
                )
            }
        )
        source_ids = sorted(
            {
                source_slice["source_id"]
                for clause_id in clause_ids
                for source_slice in self._projection.get("source_clauses", {})
                .get(clause_id, {})
                .get("source_slices", [])
            }
        )
        return self._envelope(
            ref=ref,
            rule_ids=sorted(rule_ids),
            source_clause_ids=clause_ids,
            source_ids=source_ids,
            source_bindings=[
                {
                    **dict(binding),
                    "clause_id": next(
                        (
                            clause_id
                            for clause_id in clause_ids
                            if any(
                                source_slice.get("slice_id")
                                == binding.get("slice_id")
                                for source_slice in self._projection.get(
                                    "source_clauses", {}
                                )
                                .get(clause_id, {})
                                .get("source_slices", [])
                            )
                        ),
                        None,
                    ),
                }
                for rule_id in sorted(rule_ids)
                for binding in self._projection.get(
                    "rule_source_bindings", {}
                ).get(rule_id, [])
            ],
            source_clauses=[
                _copy(self._projection.get("source_clauses", {})[clause_id])
                for clause_id in clause_ids
            ],
        )

    def edge_source_trace(self, ref: str) -> dict[str, Any]:
        edge = self._semantic_edges.get(ref)
        if edge is None:
            raise CorridorKitError(f"unknown semantic edge: {ref}")
        endpoint_rule_ids = [str(edge["from_rule_id"]), str(edge["to_rule_id"])]
        return self._envelope(
            ref=ref,
            semantic_edge=_copy(edge),
            endpoint_rule_source_traces=[
                {
                    "rule_id": rule_id,
                    "trace": {
                        key: value
                        for key, value in self.source_trace(rule_id).items()
                        if key
                        not in {
                            "ok",
                            "advisory_only",
                            "authorizes_mutation",
                            "blocking_gate",
                            "graph_digest",
                            "graph_bytes_digest",
                            "head_record_id",
                        }
                    },
                }
                for rule_id in endpoint_rule_ids
            ],
        )

    def active_context(
        self, *, max_chars: int = ACTIVE_CONTEXT_DEFAULT_MAX_CHARS
    ) -> dict[str, Any]:
        """Return one bounded semantic working set for the latest Position."""

        if not isinstance(max_chars, int) or isinstance(max_chars, bool) or max_chars < 512:
            raise CorridorKitError("active context max_chars must be an integer >= 512")
        frontier = self.frontier()
        open_checklist_ids = sorted(
            set(frontier["ready_item_ids"])
            | set(frontier["blocked_item_ids"])
            | set(frontier["unresolved_checklist_item_ids"])
        )
        if not open_checklist_ids:
            open_checklist_ids = sorted(self._projection.get("checklist_items", {}))
        related_checklist_ids = set(open_checklist_ids)
        for item_id in open_checklist_ids:
            related_checklist_ids.update(_stable_closure(item_id, self._dependencies))
            related_checklist_ids.update(self._dependants.get(item_id, frozenset()))
            related_checklist_ids.update(self._conflicts.get(item_id, frozenset()))
            related_checklist_ids.update(self._invalidates.get(item_id, frozenset()))
        related_checklist_ids.intersection_update(
            self._projection.get("checklist_items", {})
        )
        rule_ids = sorted(
            {
                str(
                    self._projection["checklist_items"][item_id]["source_rule_id"]
                )
                for item_id in related_checklist_ids
            }
        )
        semantic_edge_ids = sorted(
            edge_id
            for edge_id, edge in self._semantic_edges.items()
            if edge["from_rule_id"] in rule_ids or edge["to_rule_id"] in rule_ids
        )
        witness_obligation_ids = sorted(
            obligation_id
            for obligation_id, obligation in self._witness_obligations.items()
            if obligation["checklist_item_id"] in related_checklist_ids
        )
        hard_semantic_edge_ids = sorted(
            edge_id
            for edge_id in semantic_edge_ids
            if self._semantic_edges[edge_id]["declared_relationship"]
            in HARD_RELATIONSHIPS
        )
        hard_typed_expansion_ids = sorted(
            {
                expansion_id
                for edge_id in hard_semantic_edge_ids
                for expansion_id in self._semantic_edges[edge_id][
                    "typed_expansion_ids"
                ]
            }
        )
        unresolved_mismatch_ids = sorted(
            edge_id
            for edge_id in semantic_edge_ids
            if self._semantic_edges[edge_id][
                "relationship_expectation_status"
            ]
            == "unresolved"
            or not self._semantic_edges[edge_id]["typed_expansion_ids"]
        )
        detail_candidates: list[tuple[str, dict[str, Any]]] = []
        for edge_id in semantic_edge_ids:
            detail_candidates.append(
                (f"edge:{edge_id}", _copy(self._semantic_edges[edge_id]))
            )
        for rule_id in rule_ids:
            detail_candidates.append(
                (
                    f"rule:{rule_id}",
                    {
                        "rule_id": rule_id,
                        "rule_record_id": self._projection.get(
                            "rule_records", {}
                        ).get(rule_id),
                        "statement": self._projection.get(
                            "rule_statements", {}
                        ).get(rule_id),
                        "rule_semantics_digest": self._projection.get(
                            "rule_semantics_digests", {}
                        ).get(rule_id),
                        "source_trace": {
                            key: value
                            for key, value in self.source_trace(rule_id).items()
                            if key
                            in {
                                "source_clause_ids",
                                "source_ids",
                                "source_bindings",
                                "source_clauses",
                            }
                        },
                    },
                )
            )
        for item_id in sorted(related_checklist_ids):
            detail_candidates.append(
                (
                    f"checklist:{item_id}",
                    _copy(self._projection["checklist_items"][item_id]),
                )
            )
        for obligation_id in witness_obligation_ids:
            detail_candidates.append(
                (
                    f"witness:{obligation_id}",
                    _copy(self._witness_obligations[obligation_id]),
                )
            )
        details: list[dict[str, Any]] = []
        omitted_detail_ids: list[str] = []
        used_chars = 2
        for detail_id, detail in detail_candidates:
            entry = {"detail_id": detail_id, "detail": detail}
            encoded_chars = len(
                json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            )
            if used_chars + encoded_chars <= max_chars:
                details.append(entry)
                used_chars += encoded_chars
            else:
                omitted_detail_ids.append(detail_id)
        return self._envelope(
            latest_position_ref=frontier["latest_position_ref"],
            open_checklist_item_ids=open_checklist_ids,
            related_checklist_item_ids=sorted(related_checklist_ids),
            rule_ids=rule_ids,
            semantic_edge_ids=semantic_edge_ids,
            witness_obligation_ids=witness_obligation_ids,
            compact_hard_constraint_ids={
                "semantic_edge_ids": hard_semantic_edge_ids,
                "typed_expansion_ids": hard_typed_expansion_ids,
            },
            unresolved_mismatch_ids=unresolved_mismatch_ids,
            details=details,
            details_digest=sha256_json(details),
            max_chars=max_chars,
            encoded_detail_chars=used_chars,
            status="truncated" if omitted_detail_ids else "complete",
            omitted_detail_ids=omitted_detail_ids,
            omitted_detail_ids_digest=sha256_json(omitted_detail_ids),
        )

    def explain_blocked(self, ref: str) -> dict[str, Any]:
        frontier = self.frontier()
        return self._envelope(
            ref=ref,
            blocked=ref in frontier["blocked_item_ids"],
            prerequisite_refs=sorted(self._dependencies.get(ref, frozenset())),
            conflict_refs=sorted(self._conflicts.get(ref, frozenset())),
            invalidated_by_refs=sorted(
                source
                for source, targets in self._invalidates.items()
                if ref in targets
            ),
        )

    def rule_closure(self, rule_id: str, *, expected_digest: str | None = None) -> dict[str, Any]:
        if rule_id not in self._projection.get("rule_records", {}):
            raise CorridorKitError(f"unknown Rule: {rule_id}")
        digest = self._projection.get("rule_closures", {}).get(rule_id)
        ratified = rule_id in self._projection.get("ratified_rules", set())
        history = self._rule_history.get(rule_id, ())
        latest_type = history[-1]["record_type"] if history else None
        if digest:
            status = "successor_established"
            invalidated = False
            invalidation_reason = None
        elif ratified:
            status = "legacy_ratified"
            invalidated = False
            invalidation_reason = None
        else:
            status = "invalidated" if latest_type == "rule_revision" else "unratified"
            invalidated = status == "invalidated"
            invalidation_reason = (
                "rule_revision_after_ratification" if invalidated else None
            )
        checklist_ids = sorted(
            item_id
            for item_id, item in self._projection.get("checklist_items", {}).items()
            if item.get("source_rule_id") == rule_id
        )
        closure_identity = {
            "rule_id": rule_id,
            "rule_record_id": self._projection["rule_records"][rule_id],
            "rule_closure_digest": digest,
            "checklist_item_ids": checklist_ids,
        }
        closure_history = list(self._rule_closure_history.get(rule_id, ()))
        current_ratification = next(
            (
                item
                for item in reversed(closure_history)
                if ratified
                and item["ratification_body"].get("rule_record_id")
                == closure_identity["rule_record_id"]
            ),
            None,
        )
        previous_ratification = next(
            (
                item
                for item in reversed(closure_history)
                if current_ratification is None
                or item["ratification_record_id"]
                != current_ratification["ratification_record_id"]
            ),
            None,
        )
        current_contents = _copy(current_ratification) if current_ratification else None
        previous_contents = (
            _copy(previous_ratification) if previous_ratification else None
        )
        current_items = set(
            current_contents.get("checklist_item_ids", []) if current_contents else []
        )
        previous_items = set(
            previous_contents.get("checklist_item_ids", [])
            if previous_contents
            else []
        )
        previous_body = (
            previous_contents.get("ratification_body", {})
            if previous_contents
            else {}
        )
        return self._envelope(
            rule_id=rule_id,
            status=status,
            ratified=ratified,
            invalidated=invalidated,
            invalidation_reason=invalidation_reason,
            rule_closure_digest=digest,
            expected_digest=expected_digest,
            digest_matches=(expected_digest == digest if expected_digest else None),
            closure_identity=closure_identity,
            closure_identity_digest=sha256_json(closure_identity),
            history=[_copy(item) for item in history],
            closure_contents=current_contents,
            closure_history=[_copy(item) for item in closure_history],
            closure_diff={
                "previous_closure_contents": previous_contents,
                "current_closure_contents": current_contents,
                "rule_record_changed": (
                    previous_body.get("rule_record_id")
                    != closure_identity["rule_record_id"]
                    if previous_contents
                    else None
                ),
                "closure_digest_changed": (
                    previous_body.get("rule_closure_digest") != digest
                    if previous_contents
                    else None
                ),
                "added_checklist_item_ids": sorted(current_items - previous_items),
                "removed_checklist_item_ids": sorted(previous_items - current_items),
            },
            invalidation_impact={
                "invalidated": invalidated,
                "reason": invalidation_reason,
                "affected_dependant_refs": _stable_closure(
                    rule_id, self._historical_dependants
                ),
            },
        )

    def query(
        self,
        kind: str,
        *,
        ref: str | None = None,
        target_ref: str | None = None,
        expected_digest: str | None = None,
        max_chars: int = ACTIVE_CONTEXT_DEFAULT_MAX_CHARS,
    ) -> dict[str, Any]:
        if kind == "topology":
            return self.topology()
        if kind == "frontier":
            return self.frontier()
        if kind == "active-context":
            return self.active_context(max_chars=max_chars)
        if ref is None:
            raise CorridorKitError(f"graph query {kind} requires --ref")
        dispatch = {
            "node": self.node,
            "neighbors": self.neighbors,
            "prerequisites": self.prerequisite_closure,
            "dependants": self.dependant_closure,
            "impact": self.impact,
            "source-trace": self.source_trace,
            "edge-source-trace": self.edge_source_trace,
            "explain-blocked": self.explain_blocked,
        }
        if kind == "path":
            if target_ref is None:
                raise CorridorKitError("graph query path requires --target-ref")
            return self.path(ref, target_ref)
        if kind == "rule-closure":
            return self.rule_closure(ref, expected_digest=expected_digest)
        action = dispatch.get(kind)
        if action is None:
            raise CorridorKitError(f"unknown graph query kind: {kind}")
        return action(ref)
