from __future__ import annotations

import pytest

from helpers import database_name_from_url, require_test_database


def test_database_name_extracted_from_asyncpg_url() -> None:
    url = "postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test"
    assert database_name_from_url(url) == "sports_intel_test"


def test_require_test_database_accepts_test_suffix() -> None:
    require_test_database("postgresql+asyncpg://u:p@host:5433/sports_intel_test")


def test_require_test_database_rejects_dev_database() -> None:
    with pytest.raises(RuntimeError, match="_test"):
        require_test_database("postgresql+asyncpg://u:p@localhost:5433/sports_intel")


def test_require_test_database_rejects_empty_url() -> None:
    with pytest.raises(RuntimeError, match="_test"):
        require_test_database("")
