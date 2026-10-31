"""Validation rule families, in the order the engine runs them."""
from .base import Ref, Output, Rule, parse_edd
from .completeness import CompletenessRules
from .referential import ReferentialRules
from .structural import StructuralRules
from .preservation import PreservationRules
from .holding_time import HoldingTimeRules
from .detection import DetectionRules
from .blanks import BlankRules
from .surrogates import SurrogateRules
from .spikes import SpikeRules
from .duplicates import DuplicateRules
from .plausibility import PlausibilityRules

RULE_FAMILIES = [
    CompletenessRules, ReferentialRules, StructuralRules, PreservationRules, HoldingTimeRules,
    DetectionRules, BlankRules, SurrogateRules, SpikeRules, DuplicateRules, PlausibilityRules,
]

__all__ = ["Ref", "Output", "Rule", "parse_edd", "RULE_FAMILIES"]
