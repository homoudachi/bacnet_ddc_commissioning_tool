#!/usr/bin/env python3
"""Single entry point for commissioning BACnet operations (probe + read/write).

Runtime and future flow code should depend on :class:`CommissioningBACnetAdapter`
rather than importing ``bip_adapter`` and ``bacpypes_client`` separately. Low-level
modules remain the implementation; this module is the stable façade.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Callable


def _load_sibling_module(logical_name: str, filename: Path) -> Any:
    """Load ``filename`` as a module (same pattern as ``tools/runtime/app.py``)."""
    full_name = f"_commissioning_bacnet.{logical_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = importlib.util.spec_from_file_location(full_name, filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load module from {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


class CommissioningBACnetAdapter:
    """BACnet/IP façade: minimal UDP probe (B/IP) + BACpypes3 Read/WriteProperty."""

    #: Floor for Who-Is wait when deriving timeouts from CLI ``--timeout-seconds`` × retries.
    MIN_WHO_IS_TIMEOUT_SECONDS = 3.0
    #: Single confirmed service timeout for commissioning Read/WriteProperty (seconds).
    COMMISSIONING_APDU_TIMEOUT_SECONDS = 8.0

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root).resolve()
        self._bacnet_dir = self._repo_root / "tools" / "bacnet"
        self._bip_mod: Any | None = None
        self._client_mod: Any | None = None

    def _bip(self) -> Any:
        if self._bip_mod is None:
            self._bip_mod = _load_sibling_module(
                "bip_adapter_impl", self._bacnet_dir / "bip_adapter.py"
            )
        return self._bip_mod

    def _client(self) -> Any:
        if self._client_mod is None:
            self._client_mod = _load_sibling_module(
                "bacpypes_client_impl", self._bacnet_dir / "bacpypes_client.py"
            )
        return self._client_mod

    @property
    def present_value_property_id(self) -> int:
        return int(self._bip().BACNET_PROP_PRESENT_VALUE)

    def object_type_name_to_int(self, name: str) -> int | None:
        fn: Callable[[str], int | None] = self._bip().object_type_name_to_int
        return fn(name)

    @staticmethod
    def format_ipv4_target(host: str, port: int) -> str:
        return target_address(host, port)

    @classmethod
    def effective_who_is_timeout(cls, timeout_seconds: float, retries: int) -> float:
        """Who-Is timeout derived from probe timeout and retry count (BACpypes3 path)."""
        return max(
            cls.MIN_WHO_IS_TIMEOUT_SECONDS,
            float(timeout_seconds) * max(1, int(retries)),
        )

    @classmethod
    def commissioning_apdu_timeout_seconds(cls) -> float:
        """APDU timeout for commissioning Read/WriteProperty."""
        return float(cls.COMMISSIONING_APDU_TIMEOUT_SECONDS)

    def probe_device(
        self,
        *,
        host: str,
        port: int,
        expected_device_instance: int,
        timeout_seconds: float = 0.5,
        retries: int = 1,
    ) -> dict[str, Any]:
        return self._bip().probe_device(
            host=host,
            port=port,
            expected_device_instance=expected_device_instance,
            timeout_seconds=timeout_seconds,
            retries=retries,
        )

    def plan_write_property(
        self,
        *,
        host: str,
        port: int,
        expected_device_instance: int,
        object_type: int,
        object_instance: int,
        property_id: int,
        value: int,
        timeout_seconds: float = 0.5,
        retries: int = 1,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        return self._bip().plan_write_property(
            host=host,
            port=port,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            property_id=property_id,
            value=value,
            timeout_seconds=timeout_seconds,
            retries=retries,
            dry_run=dry_run,
        )

    def read_present_value(
        self,
        *,
        bind_port: int,
        target_address: str,
        expected_device_instance: int,
        object_type: int,
        object_instance: int,
        property_name: str = "presentValue",
        who_is_timeout: float = 3.0,
        apdu_timeout: float = 5.0,
    ) -> dict[str, Any]:
        return self._client().read_present_value(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            property_name=property_name,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )

    def write_present_value(
        self,
        *,
        bind_port: int,
        target_address: str,
        expected_device_instance: int,
        object_type: int,
        object_instance: int,
        value: int,
        who_is_timeout: float = 3.0,
        apdu_timeout: float = 5.0,
    ) -> dict[str, Any]:
        return self._client().write_present_value(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            value=value,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )


def target_address(host: str, port: int) -> str:
    """Format ``host:port`` for BACpypes3 ``IPv4Address``."""
    return f"{str(host).strip()}:{int(port)}"
