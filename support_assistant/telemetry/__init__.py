"""Operational telemetry: structured events with trace ids, per-step durations, token usage,
and cost estimated from explicit rates. Events describe what happened to a request, never how
good the draft was, and carry no customer or draft text.
"""
from .events import Event, EventSink, read_events, text_fingerprint
from .trace import Trace

__all__ = ["Event", "EventSink", "Trace", "read_events", "text_fingerprint"]
