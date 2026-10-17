import pytest

from soundmat.config import load_config


@pytest.fixture
def config():
    return load_config()
