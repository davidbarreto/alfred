"""Each finance table module must load the classes its relationships name, so importing one alone works.

Regression: importing the travel trip service into the day plan loaded `Transaction` before `Account`, and the
first mapper configuration (a module-level `selectinload` in the study repository) failed at app start-up.
"""
import subprocess
import sys

import pytest

_MODULES = [
    "app.features.finance.transactions.tables",
    "app.features.finance.accounts.tables",
    "app.features.finance.categories.tables",
    "app.features.finance.recurring_transactions.tables",
    "app.features.finance.budgets.tables",
    "app.features.finance.tags.tables",
]


@pytest.mark.parametrize("module", _MODULES)
def test_table_module_configures_its_mappers_when_imported_alone(module):
    code = f"import {module}\nfrom sqlalchemy.orm import configure_mappers\nconfigure_mappers()\n"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr.strip().splitlines()[-1]
