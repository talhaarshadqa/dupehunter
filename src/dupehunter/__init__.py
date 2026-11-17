"""dupehunter - fast, safe duplicate-file finder."""

from .actions import pick_keeper, remove_duplicates
from .core import DuplicateGroup, find_duplicates

__all__ = ["DuplicateGroup", "find_duplicates", "pick_keeper", "remove_duplicates"]
__version__ = "1.0.0"
