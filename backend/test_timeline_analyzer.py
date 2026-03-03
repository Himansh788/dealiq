"""
Unit tests for timeline_analyzer.py
Run with: python -m pytest backend/test_timeline_analyzer.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from services.timeline_analyzer import compute_delta


def test_compute_delta_basic():
    assert compute_delta(400, 1000) == 600


def test_compute_delta_decrease():
    assert compute_delta(1000, 400) == -600


def test_compute_delta_same():
    assert compute_delta(500, 500) == 0


def test_compute_delta_from_zero():
    assert compute_delta(0, 750) == 750


def test_compute_delta_floats():
    result = compute_delta(99.99, 199.99)
    assert abs(result - 100.0) < 0.001
