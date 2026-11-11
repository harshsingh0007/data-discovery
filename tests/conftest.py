import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))


@pytest.fixture
def fixture_json():
    return lambda name: json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixture_text():
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def settings():
    from discovery_agent.config import load_settings
    return load_settings()


@pytest.fixture
def uc1():
    from discovery_agent.config import load_use_case
    return load_use_case("UC1")


@pytest.fixture
def uc2():
    from discovery_agent.config import load_use_case
    return load_use_case("UC2")
