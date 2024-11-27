import pytest
from app import create_app

# Mock placeholder test; make sure reality still works,
# computation is still valid in one key case. If this test
# fails, run for the hills we're all DOOOOOOOOOOOOOOOOOOOMED
def test_reality():
    assert (1 == 1) == True

def test_app_exists():
    assert create_app() is not None