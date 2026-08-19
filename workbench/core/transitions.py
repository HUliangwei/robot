"""Lifecycle rules for coarse-grained jobs and execution attempts."""
from __future__ import annotations

from .domain import AttemptState, JobState

_JOB_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.READY, JobState.RUNNING, JobState.CANCELLED},
    JobState.READY: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
    JobState.FAILED: {JobState.READY},
    JobState.SUCCEEDED: set(),
    JobState.CANCELLED: set(),
}

_ATTEMPT_TRANSITIONS: dict[AttemptState, set[AttemptState]] = {
    AttemptState.CREATED: {AttemptState.RUNNING, AttemptState.CANCELLED},
    AttemptState.RUNNING: {AttemptState.SUCCEEDED, AttemptState.FAILED, AttemptState.CANCELLED},
    AttemptState.SUCCEEDED: set(),
    AttemptState.FAILED: set(),
    AttemptState.CANCELLED: set(),
}


def transition_job(current: JobState, target: JobState) -> JobState:
    if target not in _JOB_TRANSITIONS[current]:
        raise ValueError(f"invalid job transition: {current.value} -> {target.value}")
    return target


def transition_attempt(current: AttemptState, target: AttemptState) -> AttemptState:
    if target not in _ATTEMPT_TRANSITIONS[current]:
        raise ValueError(f"invalid attempt transition: {current.value} -> {target.value}")
    return target
