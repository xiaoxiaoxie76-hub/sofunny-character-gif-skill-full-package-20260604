"""Small easing helpers for SoFunny parameter-driven source animation."""

from __future__ import annotations

import math


SUPPORTED_CURVES = {
    "ease_in_out_sine",
    "ease_out_quad",
    "ease_out_back",
    "overshoot_settle",
    "sine_loop",
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def shifted_progress(progress: float, phase_offset: float = 0.0) -> float:
    return (progress - phase_offset) % 1.0


def ease_in_out_sine(t: float) -> float:
    t = clamp01(t)
    return -(math.cos(math.pi * t) - 1.0) / 2.0


def ease_out_quad(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_out_back(t: float) -> float:
    t = clamp01(t)
    c1 = 1.70158
    c3 = c1 + 1.0
    return 1.0 + c3 * pow(t - 1.0, 3) + c1 * pow(t - 1.0, 2)


def overshoot_settle(t: float) -> float:
    t = clamp01(t)
    if t < 0.72:
        return ease_out_back(t / 0.72)
    settle_t = (t - 0.72) / 0.28
    return 1.0 + (0.08 * math.cos(settle_t * math.pi)) * (1.0 - settle_t)


def curve_unit(curve: str, progress: float, phase_offset: float = 0.0) -> float:
    """Return a loop-friendly -1..1-ish signal for a curve family."""
    t = shifted_progress(progress, phase_offset)
    if curve == "sine_loop":
        return math.sin(math.tau * t)
    if curve == "ease_in_out_sine":
        return math.sin(math.tau * ease_in_out_sine(t))
    if curve == "ease_out_quad":
        return math.sin(math.tau * ease_out_quad(t))
    if curve == "ease_out_back":
        return math.sin(math.tau * ease_out_back(t))
    if curve == "overshoot_settle":
        return math.sin(math.tau * overshoot_settle(t))
    raise ValueError(f"unsupported easing curve: {curve}")


def curve_between(low: float, high: float, curve: str, progress: float, phase_offset: float = 0.0) -> float:
    signal = curve_unit(curve, progress, phase_offset)
    center = (low + high) / 2.0
    amplitude = (high - low) / 2.0
    return center + amplitude * signal
