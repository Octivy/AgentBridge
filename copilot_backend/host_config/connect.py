"""Unified "connect" orchestration for software bridges.

One click on "连接" runs the full chain so the user never has to read notes or
open a terminal:

    detect install -> install adapter/plugin -> start bridge process
    -> wait for host registration -> health check
    -> persist (enable + auto_start)  # 一次配置，多次可用

Every step reports ok/message so the panel can render progress and actionable
recovery hints. All steps are idempotent: connecting twice is safe.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from adapter_install.blender import install_blender_addon
from adapter_install.rhino import install_rhino_adapter
from adapter_install.sketchup import install_sketchup_extension
from host_config.detect import autocad_plugin_status, detect_installed_software
from host_config.models import HostAdapterConfig, HostConfigUpdate
from host_config.service import HostConfigService
from host_runtime.client import HostClient
from host_runtime.registry import (
    default_registry_dir,
    discover_hosts,
    list_registrations,
    remove_registration,
)

ConnectorInstaller = Callable[[], Dict[str, object]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _powershell() -> str:
    return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def default_bridge_launch(host_kind: str) -> Dict[str, object]:
    """Default launch spec for a software's bridge process (repo layout)."""

    root = _repo_root()
    scripts = {
        "autocad": ("start-cadmcp.ps1", ["CADMCP_BRIDGE_URL", "CADMCP_BRIDGE_TOKEN"]),
        "blender": ("start-hostmcp.ps1", ["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT"]),
        "sketchup": ("start-hostmcp.ps1", ["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT"]),
        "rhino": ("start-hostmcp.ps1", ["HOSTMCP_REGISTRY_DIR", "HOSTMCP_TRANSPORT"]),
    }
    script, env_vars = scripts.get(host_kind, ("start-hostmcp.ps1", []))
    return {
        "command": _powershell(),
        "args": ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts_dir(root) / script)],
        "env": {},
        "env_vars": env_vars,
        "cwd": str(root),
        "transport": "stdio",
    }


def scripts_dir(root: Path) -> Path:
    return root / "scripts"


def default_connector_installers(repo_root: Optional[Path] = None) -> Dict[str, ConnectorInstaller]:
    """Per-software adapter/plugin installers (traditional software needs a
    plugin installed once; afterwards the plugin auto-connects on launch)."""

    root = repo_root or _repo_root()
    return {
        "blender": lambda: install_blender_addon(repo_root=root),
        "sketchup": lambda: install_sketchup_extension(repo_root=root),
        "rhino": lambda: install_rhino_adapter(repo_root=root),
    }


def _step(name: str, ok: bool, message: str, detail: str = "") -> Dict[str, object]:
    return {"name": name, "ok": ok, "message": message, "detail": detail}


class HostConnector:
    """Run the full connect chain for one configured software bridge."""

    def __init__(
        self,
        service: HostConfigService,
        *,
        registry_dir: Optional[Path] = None,
        installers: Optional[Dict[str, ConnectorInstaller]] = None,
        wait_seconds: float = 8.0,
        poll_interval: float = 0.8,
        sleep: Callable[[float], None] = time.sleep,
        software_launcher: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._service = service
        self._registry_dir = Path(registry_dir or default_registry_dir())
        self._installers = installers if installers is not None else default_connector_installers()
        self._wait_seconds = wait_seconds
        self._poll_interval = poll_interval
        self._sleep = sleep
        self._software_launcher = software_launcher

    # ----- public API -----

    def connect(self, host_id: str) -> Dict[str, object]:
        config = self._service.get_config(host_id)
        if config is None:
            raise KeyError(f"host config not found: {host_id}")

        # Drop stale registrations for this software first (dead process or
        # endpoint refusing connections), so the chain never picks up a zombie.
        cleanup_stale_registrations(self._registry_dir, host_kind=config.host_kind)

        steps: List[Dict[str, object]] = []
        # "连接" is an explicit user action: a previously disabled entry (old
        # seed data) is enabled automatically instead of failing mid-chain.
        if not config.enabled:
            config = self._service.update_config(config.host_id, HostConfigUpdate(enabled=True))
            steps.append(_step("enable", True, "该软件此前处于停用状态，已自动启用"))

        detected = self._step_detect(config, steps)
        if detected is None:
            return self._result(config.host_id, steps, connected=False, persisted=False)

        self._step_install_adapter(config, detected, steps)
        self._step_start_bridge(config, steps)
        registration = self._step_wait_registration(config, steps)
        if registration is None:
            return self._result(config.host_id, steps, connected=False, persisted=False)

        if not self._step_health(config, registration, steps):
            return self._result(config.host_id, steps, connected=False, persisted=False)

        persisted = self._step_persist(config, steps)
        return self._result(config.host_id, steps, connected=True, persisted=persisted)

    # ----- steps -----

    def _step_detect(
        self, config: HostAdapterConfig, steps: List[Dict[str, object]]
    ) -> Optional[Dict[str, object]]:
        found = detect_installed_software([config.host_kind])
        entry = found[0] if found else {"detected": False, "installations": []}
        if entry.get("detected"):
            versions = ", ".join(
                str(item.get("version") or "") for item in entry.get("installations", [])[:3]
            )
            steps.append(_step("detect", True, f"已检测到 {config.name}（{versions}）"))
            return entry
        steps.append(
            _step(
                "detect",
                False,
                f"未在本机检测到 {config.name}",
                "请先安装该软件，或确认其为受支持的版本后重试。",
            )
        )
        return None

    def _step_install_adapter(
        self,
        config: HostAdapterConfig,
        detected: Dict[str, object],
        steps: List[Dict[str, object]],
    ) -> None:
        kind = config.host_kind
        if kind == "autocad":
            status = autocad_plugin_status()
            if status.get("installed"):
                steps.append(_step("install_adapter", True, "AutoCAD 插件包已安装（随 AutoCAD 启动自动加载）"))
            else:
                steps.append(
                    _step(
                        "install_adapter",
                        False,
                        "AutoCAD 插件包未安装",
                        "插件包需要从发布产物构建安装：运行仓库根目录 install.ps1（或发布包内的 "
                        "Install-AgentBridge.ps1）。安装后每次启动 AutoCAD 会自动加载，无需重复连接。",
                    )
                )
            return

        installer = self._installers.get(kind)
        if installer is None:
            steps.append(_step("install_adapter", True, f"{config.name} 无需安装适配器"))
            return

        if detected.get("adapter_installed"):
            steps.append(_step("install_adapter", True, "适配器/插件已安装，跳过重复安装"))
            return

        try:
            outcome = installer()
        except Exception as exc:  # noqa: BLE001
            steps.append(_step("install_adapter", False, f"适配器安装失败：{exc}"))
            return

        ok = bool(outcome.get("ok"))
        message = str(outcome.get("message") or ("适配器已安装" if ok else "适配器安装未完成"))
        detail = ""
        if ok:
            detail = "重启/打开软件后插件会自动注册连接；本次配置永久有效。"
        steps.append(_step("install_adapter", ok, message, detail))

    def _step_start_bridge(self, config: HostAdapterConfig, steps: List[Dict[str, object]]) -> None:
        if not config.launch.command.strip():
            launch = default_bridge_launch(config.host_kind)
            if not Path(str(launch["args"][-1])).exists():
                steps.append(_step("start_bridge", False, "桥接进程启动脚本不存在", str(launch["args"][-1])))
                return
            try:
                self._service.update_config(host_id=config.host_id, request=HostConfigUpdate(launch=launch))
            except Exception as exc:  # noqa: BLE001
                steps.append(_step("start_bridge", False, f"写入桥接启动配置失败：{exc}"))
                return
            config = self._service.get_config(config.host_id) or config

        status = self._service.status(config.host_id)
        if status.process_running:
            steps.append(_step("start_bridge", True, "桥接进程已在运行"))
            return
        try:
            self._service.start(config.host_id)
            steps.append(_step("start_bridge", True, "桥接进程已启动"))
        except (ValueError, OSError) as exc:
            steps.append(_step("start_bridge", False, f"桥接进程启动失败：{exc}"))

    def _step_wait_registration(
        self, config: HostAdapterConfig, steps: List[Dict[str, object]]
    ):
        deadline = self._wait_seconds
        elapsed = 0.0
        while elapsed <= deadline:
            registration = self._find_registration(config.host_kind)
            if registration is not None:
                steps.append(
                    _step(
                        "wait_registration",
                        True,
                        f"宿主已注册：{registration.product} {registration.product_version} @ {registration.endpoint}",
                    )
                )
                return registration
            self._sleep(self._poll_interval)
            elapsed += self._poll_interval

        launched = False
        if self._software_launcher is not None:
            try:
                launched = bool(self._software_launcher(config.host_kind))
            except Exception:  # noqa: BLE001
                launched = False
        hint = (
            f"① 现在打开或重启 {config.name}（插件/适配器会自动完成注册）；"
            "② 回到面板点“重新连接”或“测试连接”，即可看到连接状态。"
        )
        if launched:
            hint = "已尝试自动拉起软件。" + hint
        steps.append(_step("wait_registration", False, f"等待 {config.name} 注册超时", hint))
        return None

    def _step_health(
        self, config: HostAdapterConfig, registration, steps: List[Dict[str, object]]
    ) -> bool:
        try:
            health = HostClient(registration.endpoint, registration.token, timeout_seconds=5).health()
        except Exception as exc:  # noqa: BLE001
            steps.append(
                _step(
                    "health",
                    False,
                    f"健康检查失败：{exc}",
                    "注册信息可能已过期（软件重启后 token 会变化）。可清理陈旧注册后重试连接。",
                )
            )
            return False
        ok = bool(health and health.get("ok"))
        if ok:
            steps.append(_step("health", True, "健康检查通过，连接可用"))
        else:
            steps.append(_step("health", False, "宿主已注册但报告不健康", str(health)[:200]))
        return ok

    def _step_persist(self, config: HostAdapterConfig, steps: List[Dict[str, object]]) -> bool:
        try:
            self._service.update_config(
                host_id=config.host_id,
                request=HostConfigUpdate(enabled=True, auto_start=True),
            )
        except Exception as exc:  # noqa: BLE001
            steps.append(_step("persist", False, f"持久化连接配置失败：{exc}"))
            return False
        steps.append(
            _step("persist", True, "已保存连接配置：客户端启动时将自动拉起桥接，之后每次只需检查连接状态")
        )
        return True

    # ----- helpers -----

    def _find_registration(self, host_kind: str):
        registrations = [
            item for item in discover_hosts(self._registry_dir) if item.host_kind == host_kind
        ]
        return registrations[0] if registrations else None

    @staticmethod
    def _result(
        host_id: str, steps: List[Dict[str, object]], *, connected: bool, persisted: bool
    ) -> Dict[str, object]:
        first_failure = next((item for item in steps if not item["ok"]), None)
        summary = "连接成功，配置已持久化，多次可用。" if connected else (
            f"连接未完成：{first_failure['message']}" if first_failure else "连接未完成"
        )
        return {
            "host_id": host_id,
            "ok": connected,
            "connected": connected,
            "persisted": persisted,
            "steps": steps,
            "summary": summary,
        }



def cleanup_stale_registrations(
    registry_dir: Optional[Path] = None,
    *,
    host_kind: Optional[str] = None,
    probe_health: bool = True,
    probe_timeout: float = 1.5,
) -> Dict[str, object]:
    """Remove registration files that no longer represent a live host.

    A registration is stale when its owning process is gone, or when the
    process is alive but the adapter's HTTP endpoint refuses connections
    (e.g. Rhino is open but the adapter was never started this session).
    Keeps the registry honest so "检查连接状态" reflects reality.
    """

    directory = Path(registry_dir or default_registry_dir())
    removed: List[str] = []
    for registration in list_registrations(directory):
        if host_kind and registration.host_kind != host_kind:
            continue
        stale = False
        if registration.pid and not _pid_alive(registration.pid):
            stale = True
        elif probe_health and not _endpoint_alive(registration, probe_timeout):
            stale = True
        if stale:
            count = remove_registration(directory, registration.host_id, pid=registration.pid)
            if count:
                removed.append(f"{registration.host_id} (pid={registration.pid})")
    return {"removed": removed, "count": len(removed)}


def _endpoint_alive(registration, timeout: float) -> bool:
    try:
        health = HostClient(registration.endpoint, registration.token, timeout_seconds=timeout).health()
        return bool(health and health.get("ok"))
    except Exception:  # noqa: BLE001 - any failure means the endpoint is not usable
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        synchronize = 0x00100000
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


__all__ = ["HostConnector", "cleanup_stale_registrations", "default_bridge_launch", "default_connector_installers"]
