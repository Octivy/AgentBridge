"""一键安装目标软件适配器（SketchUp 扩展等）。"""

from adapter_install.sketchup import (
    build_sketchup_rbz,
    install_sketchup_extension,
    sketchup_extension_status,
)

__all__ = ["build_sketchup_rbz", "install_sketchup_extension", "sketchup_extension_status"]
