import pytest

from workbench.core.domain import JobState
from workbench.core.transitions import transition_job


def test_job_can_move_from_pending_to_running():
    assert transition_job(JobState.PENDING, JobState.RUNNING) is JobState.RUNNING


def test_terminal_job_cannot_return_to_running():
    with pytest.raises(ValueError, match="invalid job transition"):
        transition_job(JobState.SUCCEEDED, JobState.RUNNING)
