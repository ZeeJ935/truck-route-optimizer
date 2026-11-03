"""Gunicorn settings for the hosted backend (Render free web service).

A long route analysis can take 10-20 seconds, and a free instance that has been
sleeping can need up to a minute to wake, so the worker timeout is generous.
One worker with several threads keeps the in-memory provider caches shared and
memory use low on a small instance.
"""

import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
threads = 4
timeout = 120
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"
