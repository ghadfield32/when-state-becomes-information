"""Fail-closed accounting, declared lineage, timing, and reviewer-support checks.

These checks do not prove label truth, clock synchronization, or video contents.
They validate supplied declarations, not the completeness of undeclared lineage
or the accuracy of timestamps. Freeze expected cohort keys before predictions;
reconciliation cannot prove when the caller chose that cohort.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Hashable, Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any


class EvidenceContractError(ValueError):
    """All detected violations; missing predictions are INCOMPLETE, never a score."""

    def __init__(self, codes: Iterable[str], *, lineage_conflicts=()) -> None:
        self.codes = tuple(sorted(set(codes)))
        self.status = "INCOMPLETE" if "missing_key" in self.codes else "INVALID"
        self.lineage_conflicts = tuple(sorted(lineage_conflicts))
        super().__init__(f"{self.status}: {', '.join(self.codes)}"
                         + (f"; lineage_conflicts={self.lineage_conflicts!r}" if self.lineage_conflicts else ""))


@dataclass(frozen=True)
class CohortReport:
    expected_count: int
    accepted_count: int
    rejected_count: int
    rejection_reasons: tuple[tuple[str, int], ...]
    status: str = "complete"

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "rejection_reasons": dict(self.rejection_reasons)}


def reconcile_cohort(
    expected_keys: Iterable[Hashable], accepted_keys: Iterable[Hashable],
    rejected: Mapping[Hashable, str] | Iterable[tuple[Hashable, str]], *, wildcard_axes=(),
) -> CohortReport:
    """Account exactly once for frozen hashable keys; rejection rows are (key, reason).

    Use an iterable of pairs to retain duplicate rejection rows. Tuple-key axes
    are zero-based; None is a wildcard only in rejections on declared axes.
    Counts/reasons count expected keys, not wildcard patterns. Failures remain
    rejected members of the cohort, never dropped from its denominator.
    """
    expected = tuple(expected_keys)
    accepted = tuple(accepted_keys)
    rejections = tuple(rejected.items() if isinstance(rejected, Mapping) else rejected)
    axes = tuple(wildcard_axes)
    if any(type(axis) is not int or axis < 0 for axis in axes):
        raise EvidenceContractError(("invalid_wildcard_axis",))
    codes = set()
    expected_set = set(expected)
    accepts = Counter(accepted)
    rejects: Counter = Counter()
    reasons: Counter = Counter()
    if not expected:
        codes.add("empty_cohort")
    if len(expected_set) != len(expected) or any(n > 1 for n in accepts.values()):
        codes.add("duplicate_key")
    if set(accepted) - expected_set:
        codes.add("unexpected_key")
    rejection_keys = Counter(key for key, _ in rejections)
    if any(n > 1 for n in rejection_keys.values()):
        codes.add("duplicate_key")
    for pattern, reason in rejections:
        valid_reason = isinstance(reason, str) and bool(reason.strip())
        if not valid_reason:
            codes.add("blank_rejection_reason")
        matches = []
        for key in expected_set:
            if isinstance(pattern, tuple) and isinstance(key, tuple):
                matched = len(pattern) == len(key) and all(
                    a == b or (a is None and i in axes)
                    for i, (a, b) in enumerate(zip(pattern, key))
                )
            else:
                matched = pattern == key
            if matched:
                matches.append(key)
        if not matches:
            codes.add("unexpected_key")
        for key in matches:
            rejects[key] += 1
            if valid_reason:
                reasons[reason.strip()] += 1
    if any(n > 1 for n in rejects.values()):
        codes.add("duplicate_key")
    if set(accepts) & set(rejects):
        codes.add("overlapping_accept_reject")
    if expected_set - set(accepts) - set(rejects):
        codes.add("missing_key")
    if codes:
        raise EvidenceContractError(codes)
    return CohortReport(len(expected), len(accepted), sum(rejects.values()), tuple(sorted(reasons.items())))


@dataclass(frozen=True)
class EvidenceAuditReport:
    row_count: int
    status: str = "complete"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_lineage_splits(rows: Iterable[Mapping[str, Any]]) -> EvidenceAuditReport:
    """Validate id, split, and nonempty namespaced lineage_groups with an event token."""
    rows = tuple(rows)
    codes = set()
    ids = set()
    groups = defaultdict(set)
    for row in rows:
        identifier = row.get("id")
        if identifier is None:
            codes.add("missing_key")
        elif identifier in ids:
            codes.add("duplicate_key")
        ids.add(identifier)
        split = row.get("split")
        if split not in ("train", "validation", "test"):
            codes.add("unknown_split")
        tokens = row.get("lineage_groups", ())
        if tokens is None or isinstance(tokens, str):
            codes.add("unnamespaced_lineage_token")
            tokens = ()
        has_event = False
        for token in tokens:
            if not isinstance(token, str) or ":" not in token:
                codes.add("unnamespaced_lineage_token")
                continue
            namespace, value = token.split(":", 1)
            if not namespace.strip() or not value.strip() or token != token.strip():
                codes.add("unnamespaced_lineage_token")
                continue
            has_event |= namespace == "event"
            if split in ("train", "validation", "test"):
                groups[token].add(split)
        if not has_event:
            codes.add("missing_event_lineage")
    conflicts = tuple(sorted((token, tuple(sorted(splits))) for token, splits in groups.items() if len(splits) > 1))
    if conflicts:
        codes.add("lineage_group_crosses_splits")
    if codes:
        raise EvidenceContractError(codes, lineage_conflicts=conflicts)
    return EvidenceAuditReport(len(rows))


def audit_temporal_evidence(
    rows: Iterable[Mapping[str, Any]], *, clock_id: str, observation_cutoff_ns: int,
    decision_time_ns: int, boundary_uncertainty_ns: int = 0,
) -> EvidenceAuditReport:
    """Rows declare clock_id, start_ns, end_ns, available_ns in one integer-ns clock.

    Availability is mandatory, including for labels written after the event.
    No availability timestamp is inferred from an observation timestamp.
    Uncertainty is nonnegative and applies conservatively to both upper bounds.
    """
    rows = tuple(rows)
    codes = set()
    if not rows:
        codes.add("empty_evidence")
    cutoff_ok = type(observation_cutoff_ns) is int
    decision_ok = type(decision_time_ns) is int
    uncertainty_ok = type(boundary_uncertainty_ns) is int
    if not all((cutoff_ok, decision_ok, uncertainty_ok)):
        codes.add("non_integer_time")
    if uncertainty_ok and boundary_uncertainty_ns < 0:
        codes.add("negative_boundary_uncertainty")
        uncertainty_ok = False
    if cutoff_ok and decision_ok and decision_time_ns < observation_cutoff_ns:
        codes.add("decision_before_cutoff")
    for row in rows:
        if not isinstance(clock_id, str) or not clock_id.strip() or row.get("clock_id") != clock_id:
            codes.add("clock_mismatch")
        start, end, available = (row.get(k) for k in ("start_ns", "end_ns", "available_ns"))
        start_ok, end_ok, available_ok = (type(t) is int for t in (start, end, available))
        if available is None:
            codes.add("missing_availability_time")
        if not start_ok or not end_ok or (available is not None and not available_ok):
            codes.add("non_integer_time")
        if start_ok and end_ok and start > end:
            codes.add("inverted_interval")
        if end_ok and available_ok and available < end:
            codes.add("available_before_observed")
        if end_ok and cutoff_ok and uncertainty_ok and end + boundary_uncertainty_ns > observation_cutoff_ns:
            codes.add("exceeds_observation_cutoff")
        if available_ok and decision_ok and uncertainty_ok and available + boundary_uncertainty_ns > decision_time_ns:
            codes.add("unavailable_at_decision")
    if codes:
        raise EvidenceContractError(codes)
    return EvidenceAuditReport(len(rows))


@dataclass(frozen=True)
class ClaimSupportReport:
    status_counts: tuple[tuple[str, int], ...]
    audited_claim_count: int
    answer_count: int
    abstained_answer_count: int
    supported_fraction: float | None
    reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "status_counts": dict(self.status_counts)}


def summarize_claim_support(reviews: Iterable[Mapping[str, Any]], answers: Iterable[Mapping[str, Any]]) -> ClaimSupportReport:
    """Statuses are reviewer outcomes, never produced by the model under evaluation.

    Each review is one claim with a status; each answer has an explicit boolean
    abstained field. The caller supplies the complete audited review population.
    not_applicable is excluded; unobservable and unverifiable remain in the
    factual-claim denominator. Abstentions count answers, not factual claims.
    """
    statuses = ("supported", "contradicted", "unverifiable", "unobservable", "not_applicable")
    counts = Counter({status: 0 for status in statuses})
    codes = set()
    for review in reviews:
        status = review.get("status")
        if status not in statuses:
            codes.add("unknown_claim_status")
        else:
            counts[status] += 1
    answers = tuple(answers)
    abstained = 0
    for answer in answers:
        if type(answer.get("abstained")) is not bool:
            codes.add("invalid_abstention")
        elif answer["abstained"]:
            abstained += 1
    if codes:
        raise EvidenceContractError(codes)
    denominator = sum(counts.values()) - counts["not_applicable"]
    return ClaimSupportReport(tuple(sorted(counts.items())), denominator, len(answers), abstained,
                              counts["supported"] / denominator if denominator else None,
                              None if denominator else "no_audited_claims")
