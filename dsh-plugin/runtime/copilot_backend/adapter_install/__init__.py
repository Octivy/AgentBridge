"""一键安装目标软件适配器（SketchUp 扩展等）。"""

from adapter_install.sketchup import (
    build_sketchup_rbz,
    install_sketchup_extension,
    sketchup_extension_status,
)
from adapter_install.rhino import install_rhino_adapter, rhino_adapter_status

__all__ = [
    "build_sketchup_rbz",
    "install_rhino_adapter",
    "install_sketchup_extension",
    "rhino_adapter_status",
    "sketchup_extension_status",
]
