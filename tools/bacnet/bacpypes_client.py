"""BACpypes3 client helpers for commissioning writes (optional dependency)."""

from __future__ import annotations

import asyncio
from typing import Any

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.local.device import DeviceObject
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, Unsigned
from bacpypes3.pdu import IPv4Address

from bacpypes3.ipv4.app import NormalApplication


def _object_type_tag(object_type: int) -> str:
    """Map BACnet object type integer to BACpypes3 parseable tag (ASHRAE standard types)."""
    # Standard object type names used in profiles / BACnet.
    names = {
        0: "analogInput",
        1: "analogOutput",
        2: "analogValue",
        3: "binaryInput",
        4: "binaryOutput",
        5: "binaryValue",
        19: "multiStateValue",
    }
    name = names.get(object_type)
    if not name:
        raise ValueError(f"unsupported object_type for write client: {object_type}")
    return name


async def _write_present_value_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    value: int,
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Run Who-Is to populate device info, then WriteProperty present-value."""
    local_device_instance = 999000 + (bind_port % 900000)
    # Construct inside async so bacpypes3 Object._post_init scheduling sees a running loop.
    device = DeviceObject(
        objectIdentifier=ObjectIdentifier(("device", local_device_instance)),
        objectName=CharacterString("commissioning-tool-client"),
    )
    app = NormalApplication(device, IPv4Address(f"0.0.0.0:{bind_port}"))

    try:
        await asyncio.sleep(0.05)
        who_future = app.who_is(
            low_limit=expected_device_instance,
            high_limit=expected_device_instance,
            address=IPv4Address(target_address),
            timeout=who_is_timeout,
        )
        iams = await asyncio.wait_for(who_future, timeout=who_is_timeout + 1.0)
        if not iams:
            return {"status": "blocked_probe_failed", "message": "no I-Am from target"}

        dest = IPv4Address(target_address)
        obj_tag = f"{_object_type_tag(object_type)} {object_instance}"
        # MSV / AV / AO present-value uses Unsigned in standard profiles for these writes.
        result = await asyncio.wait_for(
            app.write_property(dest, obj_tag, "presentValue", Unsigned(value)),
            timeout=apdu_timeout,
        )
        if isinstance(result, ErrorRejectAbortNack):
            return {
                "status": "write_rejected",
                "message": str(result),
                "detail": repr(result),
            }
        if result is None:
            return {"status": "write_ok", "message": "simple ack"}
        return {"status": "write_unexpected_response", "message": repr(result)}
    finally:
        app.close()


async def _read_present_value_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    property_name: str,
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Who-Is to populate cache, then ReadProperty."""
    local_device_instance = 999000 + (bind_port % 900000)
    device = DeviceObject(
        objectIdentifier=ObjectIdentifier(("device", local_device_instance)),
        objectName=CharacterString("commissioning-tool-client"),
    )
    app = NormalApplication(device, IPv4Address(f"0.0.0.0:{bind_port}"))

    try:
        await asyncio.sleep(0.05)
        who_future = app.who_is(
            low_limit=expected_device_instance,
            high_limit=expected_device_instance,
            address=IPv4Address(target_address),
            timeout=who_is_timeout,
        )
        iams = await asyncio.wait_for(who_future, timeout=who_is_timeout + 1.0)
        if not iams:
            return {"status": "blocked_probe_failed", "message": "no I-Am from target"}

        dest = IPv4Address(target_address)
        obj_tag = f"{_object_type_tag(object_type)} {object_instance}"
        value = await asyncio.wait_for(
            app.read_property(dest, obj_tag, property_name),
            timeout=apdu_timeout,
        )
        if isinstance(value, ErrorRejectAbortNack):
            return {
                "status": "read_rejected",
                "message": str(value),
                "detail": repr(value),
            }
        return {"status": "read_ok", "value": repr(value), "value_str": str(value)}
    finally:
        app.close()


def read_present_value(
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
    """Synchronous ReadProperty wrapper."""
    return asyncio.run(
        _read_present_value_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            property_name=property_name,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )
    )


def write_present_value(
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
    """Synchronous wrapper for CLI / subprocess callers."""
    return asyncio.run(
        _write_present_value_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            value=value,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )
    )
