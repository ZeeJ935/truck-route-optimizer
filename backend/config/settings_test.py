"""Settings for the automated test suite (local-dev mode, no provider keys required)."""

import os

os.environ.setdefault("DJANGO_DEBUG", "true")

from .settings import *  # noqa: E402,F401,F403
