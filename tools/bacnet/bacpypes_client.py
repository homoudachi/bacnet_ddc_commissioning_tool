"""BACpypes3 client helpers for commissioning writes (optional dependency)."""

from __future__ import annotations

import asyncio
from typing import Any

from bacpypes3.apdu import ErrorRejectAbortNack
from bacpypes3.local.device import DeviceObject
from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, Real, Unsigned
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


def _encode_present_value_write(object_type: int, object_instance: int, value: int | float):
    """Pick BACnet primitive for present-value write (MSV uses Unsigned; analog types use Real)."""
    # multiStateValue (19) state numbers are integral in our profiles
    if object_type == 19:
        return Unsigned(int(round(float(value))))
    return Real(float(value))


async def _write_present_value_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    value: int | float,
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
        # ObjectIdentifier parsing expects "type,instance" (not a space separator).
        obj_tag = f"{_object_type_tag(object_type)},{object_instance}"
        payload = _encode_present_value_write(object_type, object_instance, value)
        result = await asyncio.wait_for(
            app.write_property(dest, obj_tag, "presentValue", payload),
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
        obj_tag = f"{_object_type_tag(object_type)},{object_instance}"
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


def _read_property_tag(property_name: str) -> str:
    """Map profile-style names to BACpypes3 parseable property tags for RPM."""
    key = str(property_name or "").strip() or "presentValue"
    if "-" in key:
        return key
    mapping = {
        "presentValue": "present-value",
        "relinquishDefault": "relinquish-default",
        "covIncrement": "cov-increment",
        "eventState": "event-state",
        "outOfService": "out-of-service",
        "units": "units",
    }
    return mapping.get(key, key)


async def _read_present_values_batch_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    reads: list[tuple[int, int, str]],
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Sequential ReadProperty on one device after a single Who-Is."""
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
        rows: list[dict[str, Any]] = []
        for object_type, object_instance, property_name in reads:
            obj_tag = f"{_object_type_tag(object_type)},{object_instance}"
            value = await asyncio.wait_for(
                app.read_property(dest, obj_tag, property_name),
                timeout=apdu_timeout,
            )
            row: dict[str, Any] = {
                "object_type": object_type,
                "object_instance": object_instance,
                "property": property_name,
            }
            if isinstance(value, ErrorRejectAbortNack):
                row["status"] = "read_rejected"
                row["message"] = str(value)
                rows.append(row)
                return {
                    "status": "batch_partial_failure",
                    "bacnet_service": "readProperty",
                    "reads": rows,
                    "message": f"read failed at {obj_tag}",
                }
            row["status"] = "read_ok"
            row["value"] = value
            row["value_str"] = str(value)
            rows.append(row)
        return {"status": "batch_ok", "bacnet_service": "readProperty", "reads": rows}
    finally:
        app.close()


def read_present_values_batch(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    reads: list[tuple[int, int, str]],
    who_is_timeout: float = 3.0,
    apdu_timeout: float = 8.0,
) -> dict[str, Any]:
    return asyncio.run(
        _read_present_values_batch_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            reads=reads,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )
    )


async def _read_present_values_property_multiple_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    reads: list[tuple[int, int, str]],
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Single ReadPropertyMultiple confirmed service (flat parameter list per BACpypes3)."""
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
        parameter_list: list[ObjectIdentifier | list[str]] = []
        for object_type, object_instance, property_name in reads:
            parameter_list.append(ObjectIdentifier((object_type, object_instance)))
            parameter_list.append([_read_property_tag(property_name)])

        raw = await asyncio.wait_for(
            app.read_property_multiple(dest, parameter_list),
            timeout=apdu_timeout,
        )
        if isinstance(raw, ErrorRejectAbortNack):
            return {
                "status": "read_rejected",
                "message": str(raw),
                "detail": repr(raw),
                "bacnet_service": "readPropertyMultiple",
            }
        if raw is None:
            return {
                "status": "read_unexpected_response",
                "message": "null ReadPropertyMultiple response",
                "bacnet_service": "readPropertyMultiple",
            }
        if not isinstance(raw, list):
            return {
                "status": "read_unexpected_response",
                "message": repr(raw),
                "bacnet_service": "readPropertyMultiple",
            }

        by_key: dict[tuple[int, int, str], Any] = {}
        for item in raw:
            if not isinstance(item, tuple) or len(item) < 4:
                continue
            oid, prop_id, _array_index, value = item[0], item[1], item[2], item[3]
            try:
                ot_i, oi_i = int(oid[0]), int(oid[1])
            except (TypeError, ValueError):
                continue
            ptag = str(prop_id).strip()
            by_key[(ot_i, oi_i, ptag)] = value

        rows: list[dict[str, Any]] = []
        for object_type, object_instance, property_name in reads:
            tag = _read_property_tag(property_name)
            err_or_val = by_key.get((object_type, object_instance, tag))
            if err_or_val is None:
                err_or_val = by_key.get((object_type, object_instance, str(property_name).strip()))
            row: dict[str, Any] = {
                "object_type": object_type,
                "object_instance": object_instance,
                "property": property_name,
            }
            if err_or_val is None:
                row["status"] = "read_missing_in_ack"
            elif hasattr(err_or_val, "errorClass"):
                row["status"] = "read_property_error"
                row["message"] = str(err_or_val)
            else:
                row["status"] = "read_ok"
                row["value"] = err_or_val
                row["value_str"] = str(err_or_val)
            rows.append(row)

        all_ok = all(r.get("status") == "read_ok" for r in rows)
        return {
            "status": "batch_ok" if all_ok else "batch_partial",
            "bacnet_service": "readPropertyMultiple",
            "reads": rows,
        }
    finally:
        app.close()


def read_present_values_property_multiple(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    reads: list[tuple[int, int, str]],
    who_is_timeout: float = 3.0,
    apdu_timeout: float = 8.0,
) -> dict[str, Any]:
    return asyncio.run(
        _read_present_values_property_multiple_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            reads=reads,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )
    )


async def _subscribe_cov_unconfirmed_wait_value_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    subscriber_process_id: int,
    lifetime_seconds: int,
    wait_seconds: float,
    who_is_timeout: float,
) -> dict[str, Any]:
    """SubscribeCOV (unconfirmed notifications), return first present-value from notify."""
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
        monitored = ObjectIdentifier((object_type, object_instance))
        async with app.change_of_value(
            dest,
            monitored,
            subscriber_process_identifier=subscriber_process_id,
            issue_confirmed_notifications=False,
            lifetime=int(lifetime_seconds),
        ) as scm:
            _prop_id, val = await asyncio.wait_for(scm.get_value(), timeout=wait_seconds)
            return {"status": "cov_ok", "value_str": str(val), "value_repr": repr(val)}
    finally:
        app.close()


def subscribe_cov_unconfirmed_wait_value(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    subscriber_process_id: int = 4242,
    lifetime_seconds: int = 60,
    wait_seconds: float = 6.0,
    who_is_timeout: float = 3.0,
) -> dict[str, Any]:
    """Synchronous SubscribeCOV + wait for first unconfirmed notification presentValue."""
    return asyncio.run(
        _subscribe_cov_unconfirmed_wait_value_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            object_type=object_type,
            object_instance=object_instance,
            subscriber_process_id=subscriber_process_id,
            lifetime_seconds=lifetime_seconds,
            wait_seconds=wait_seconds,
            who_is_timeout=who_is_timeout,
        )
    )


async def _write_present_values_batch_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    writes: list[tuple[int, int, int | float]],
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Sequential WriteProperty present-value on one device (single Who-Is)."""
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
        results: list[dict[str, Any]] = []
        for object_type, object_instance, value in writes:
            obj_tag = f"{_object_type_tag(object_type)},{object_instance}"
            payload = _encode_present_value_write(object_type, object_instance, value)
            result = await asyncio.wait_for(
                app.write_property(dest, obj_tag, "presentValue", payload),
                timeout=apdu_timeout,
            )
            row: dict[str, Any] = {
                "object_type": object_type,
                "object_instance": object_instance,
            }
            if isinstance(result, ErrorRejectAbortNack):
                row["status"] = "write_rejected"
                row["message"] = str(result)
                results.append(row)
                return {
                    "status": "batch_partial_failure",
                    "writes": results,
                    "message": f"write failed at {obj_tag}",
                }
            if result is None:
                row["status"] = "write_ok"
            else:
                row["status"] = "write_unexpected_response"
                row["message"] = repr(result)
            results.append(row)
        return {"status": "batch_ok", "writes": results}
    finally:
        app.close()


def write_present_values_batch(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    writes: list[tuple[int, int, int | float]],
    who_is_timeout: float = 3.0,
    apdu_timeout: float = 8.0,
) -> dict[str, Any]:
    return asyncio.run(
        _write_present_values_batch_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            writes=writes,
            who_is_timeout=who_is_timeout,
            apdu_timeout=apdu_timeout,
        )
    )


async def _write_present_values_property_multiple_async(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    writes: list[tuple[int, int, int | float]],
    who_is_timeout: float,
    apdu_timeout: float,
) -> dict[str, Any]:
    """Single WritePropertyMultiple confirmed service (one APDU) for presentValue."""
    from bacpypes3.apdu import WritePropertyMultipleRequest
    from bacpypes3.basetypes import PropertyIdentifier, PropertyValue, WriteAccessSpecification
    from bacpypes3.constructeddata import Any, SequenceOf

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
        access_specs: list[Any] = []
        rows: list[dict[str, Any]] = []
        for object_type, object_instance, value in writes:
            payload = _encode_present_value_write(object_type, object_instance, value)
            prop_val = PropertyValue(
                propertyIdentifier=PropertyIdentifier("present-value"),
                value=Any(payload),
            )
            access_specs.append(
                WriteAccessSpecification(
                    objectIdentifier=ObjectIdentifier((object_type, object_instance)),
                    listOfProperties=SequenceOf(PropertyValue)([prop_val]),
                )
            )
            rows.append(
                {
                    "object_type": object_type,
                    "object_instance": object_instance,
                    "status": "pending",
                }
            )

        wpm = WritePropertyMultipleRequest(
            listOfWriteAccessSpecs=SequenceOf(WriteAccessSpecification)(access_specs),
            destination=dest,
        )
        result = await asyncio.wait_for(app.request(wpm), timeout=apdu_timeout)
        if isinstance(result, ErrorRejectAbortNack):
            return {
                "status": "write_rejected",
                "message": str(result),
                "detail": repr(result),
                "bacnet_service": "writePropertyMultiple",
                "writes": rows,
            }
        if result is None:
            for r in rows:
                r["status"] = "write_ok"
            return {
                "status": "batch_ok",
                "bacnet_service": "writePropertyMultiple",
                "writes": rows,
            }
        return {
            "status": "write_unexpected_response",
            "message": repr(result),
            "bacnet_service": "writePropertyMultiple",
            "writes": rows,
        }
    finally:
        app.close()


def write_present_values_property_multiple(
    *,
    bind_port: int,
    target_address: str,
    expected_device_instance: int,
    writes: list[tuple[int, int, int | float]],
    who_is_timeout: float = 3.0,
    apdu_timeout: float = 8.0,
) -> dict[str, Any]:
    return asyncio.run(
        _write_present_values_property_multiple_async(
            bind_port=bind_port,
            target_address=target_address,
            expected_device_instance=expected_device_instance,
            writes=writes,
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
    value: int | float,
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
