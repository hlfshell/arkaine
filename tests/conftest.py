import os
import sys
import warnings

import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def ignore_module_warnings():
    # Ignore all importlib bootstrap warnings
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, module="importlib._bootstrap"
    )

    # Ignore all SwigPy related warnings
    warnings.filterwarnings(
        "ignore", message=".*SwigPyPacked.*", category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore", message=".*SwigPyObject.*", category=DeprecationWarning
    )
    warnings.filterwarnings(
        "ignore", message=".*swigvarlink.*", category=DeprecationWarning
    )

    # General module attribute warning
    warnings.filterwarnings(
        "ignore",
        message="builtin type.*has no __module__ attribute",
        category=DeprecationWarning,
    )
