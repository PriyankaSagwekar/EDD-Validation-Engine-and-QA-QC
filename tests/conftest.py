from datetime import datetime

import pytest

from eddqc.engine import validate_frame
from eddqc.rules import Ref
from eddqc.simulate import Simulator, build_events

NOW = datetime(2026, 10, 31)


@pytest.fixture(scope="session")
def ref():
    return Ref.from_refdata()


@pytest.fixture(scope="session")
def clean_gw():
    """One clean groundwater EDD (as text) to modify in edge-case tests."""
    return Simulator(7).build_event("2601", "GW", datetime(2026, 1, 13)).df


@pytest.fixture(scope="session")
def dirty_events():
    return build_events(seed=42)


@pytest.fixture
def validate(ref):
    return lambda df: validate_frame(df, ref, NOW)
