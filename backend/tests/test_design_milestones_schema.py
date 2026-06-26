"""Regression: DesignMilestonesResponse must accept past estimated dates.

Bug: `DesignMilestonesResponse` inherited the input-only "estimated dates can't
be in the past" validator, so serializing a *stored* design whose estimated
milestone dates had naturally passed raised a ValidationError -> 500. It surfaced
when a SUPER_ADMIN used the tenant filter to view an older tenant's designs
(GET /designs and /designs/ops/submissions). The past-date rule is correct for
input only; reading data back must always succeed.
"""
import pytest
from pydantic import ValidationError

from app.schemas.designs import (
    DesignMilestonesInput,
    DesignMilestonesResponse,
    NetworkDesignSummaryResponse,
)

PAST = '2020-01-01'
FUTURE = '2999-01-01'


def test_response_accepts_past_estimated_dates():
    m = DesignMilestonesResponse(
        estimatedReviewDate=PAST,
        estimatedProposalDate=PAST,
        estimatedFulfillmentDate=PAST,
        estimatedInstallationDate=PAST,
    )
    assert m.estimated_review_date == PAST
    assert m.estimated_installation_date == PAST


def test_input_still_rejects_past_estimated_dates():
    with pytest.raises(ValidationError):
        DesignMilestonesInput(estimatedReviewDate=PAST)


def test_input_accepts_future_estimated_dates():
    assert DesignMilestonesInput(estimatedReviewDate=FUTURE).estimated_review_date == FUTURE


def test_both_reject_bad_date_format():
    for model in (DesignMilestonesInput, DesignMilestonesResponse):
        with pytest.raises(ValidationError):
            model(estimatedReviewDate='not-a-date')


def test_confirmed_dates_may_be_in_the_past_on_input():
    # confirmed_* records what actually happened, so backdating is allowed even on input.
    m = DesignMilestonesInput(confirmedInstallationDate=PAST)
    assert m.confirmed_installation_date == PAST


def test_summary_response_serializes_aged_milestones():
    """The exact 500 path: a summary built from a persisted design whose
    estimated dates are in the past must validate."""
    summary = NetworkDesignSummaryResponse(
        id='d1',
        status='in_review',
        estimatedCapex=1000.0,
        apCount=3,
        switchCount=1,
        milestones=DesignMilestonesResponse(
            estimatedReviewDate='2026-06-11',
            estimatedProposalDate='2026-06-14',
            estimatedFulfillmentDate='2026-06-21',
            estimatedInstallationDate='2026-06-25',
        ),
        createdAt='2026-06-01T00:00:00Z',
        updatedAt='2026-06-01T00:00:00Z',
    )
    assert summary.milestones.estimated_review_date == '2026-06-11'
