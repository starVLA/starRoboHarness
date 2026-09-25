"""Compatibility namespace for earlier public starRoboHarness installations."""

import sys

import starharness as _implementation

__path__ = _implementation.__path__
__all__ = _implementation.__all__
__version__ = _implementation.__version__

for _name in __all__:
    globals()[_name] = getattr(_implementation, _name)

# Share the already loaded contracts so mixed imports preserve type identity.
for _name, _module in list(sys.modules.items()):
    if _name.startswith("starharness."):
        sys.modules[__name__ + _name[len("starharness"):]] = _module
