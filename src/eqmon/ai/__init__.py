"""Local-inference layer: LM Studio client, tool wrappers, orchestration.

This package contains **no seismology**. Every number it reports comes from the
pure domain modules (analytics, aftershock, impact, intensity, contours,
exposure); the model's job is selecting tools, filling their arguments, and
writing prose. If a formula appears in here, it is in the wrong place.

Nothing in this package is on the critical path: with LM Studio stopped, every
existing endpoint behaves exactly as before.
"""
