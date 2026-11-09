"""Offline model of CVE-2026-110634 (git-diff command injection via hash-object)."""
from .model import HEADER, Outcome, evaluate, post_argv, pre_command

__all__ = ["HEADER", "Outcome", "evaluate", "post_argv", "pre_command"]
