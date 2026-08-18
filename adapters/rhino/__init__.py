"""AgentBridge Rhino host adapter package.

Required so ``import agentbridge_rhino.background_host`` works on Python 2.7
(Rhino 6 / IronPython), which has no PEP 420 namespace packages.
"""

from __future__ import absolute_import, division, print_function
