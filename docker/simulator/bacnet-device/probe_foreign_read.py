#!/usr/bin/env python3
"""Foreign-device BACnet client for BBMD lab: register, then ReadProperty.

Run with ``network_mode: service:<bbmd>`` so this process shares the BBMD
container network namespace. Registers with the local BBMD UDP port, then
reads ``presentValue`` from a target ``host:port`` (isolated subnet device).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


async def _amain() -> None:
    from bacpypes3.apdu import ErrorRejectAbortNack
    from bacpypes3.basetypes import Segmentation
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, Unsigned
    from bacpypes3.pdu import IPv4Address
    from bacpypes3.ipv4.app import ForeignApplication

    bbmd_host = os.environ.get("BACNET_FD_BBMD_HOST", "127.0.0.1").strip()
    bbmd_port = _env_int("BACNET_FD_BBMD_PORT", 47830)
    ttl = _env_int("BACNET_FD_TTL_SECONDS", 60)

    target = os.environ.get("BACNET_FD_TARGET", "").strip()
    if not target:
        raise SystemExit("BACNET_FD_TARGET required (e.g. 172.29.0.10:47808)")
    dev_lo = _env_int("BACNET_FD_DEVICE_LOW", 21004)
    dev_hi = _env_int("BACNET_FD_DEVICE_HIGH", 21004)
    obj_tag = os.environ.get("BACNET_FD_OBJECT", "analogInput,2").strip()
    who_timeout = float(os.environ.get("BACNET_FD_WHOIS_TIMEOUT", "4.0"))
    apdu_timeout = float(os.environ.get("BACNET_FD_APDU_TIMEOUT", "8.0"))

    local_device_instance = 999800
    device = DeviceObject(
        objectIdentifier=ObjectIdentifier(("device", local_device_instance)),
        objectName=CharacterString("bacnet-lab-fd-probe"),
        maxAPDULengthAccepted=Unsigned(1476),
        segmentationSupported=Segmentation("noSegmentation"),
        vendorID=Unsigned(0),
    )
    app = ForeignApplication(device, IPv4Address("0.0.0.0:0"))
    await asyncio.sleep(0.05)
    app.register(IPv4Address(f"{bbmd_host}:{bbmd_port}"), ttl)
    await asyncio.sleep(0.5)

    who_future = app.who_is(
        low_limit=dev_lo,
        high_limit=dev_hi,
        address=IPv4Address(target),
        timeout=who_timeout,
    )
    iams = await asyncio.wait_for(who_future, timeout=who_timeout + 1.0)
    if not iams:
        print(json.dumps({"status": "blocked_probe_failed", "message": "no I-Am"}))
        app.unregister()
        app.close()
        raise SystemExit(2)

    dest = IPv4Address(target)
    value = await asyncio.wait_for(
        app.read_property(dest, obj_tag, "presentValue"),
        timeout=apdu_timeout,
    )
    if isinstance(value, ErrorRejectAbortNack):
        print(
            json.dumps(
                {
                    "status": "read_rejected",
                    "message": str(value),
                }
            )
        )
        app.unregister()
        app.close()
        raise SystemExit(2)
    print(
        json.dumps(
            {
                "status": "read_ok",
                "target": target,
                "object": obj_tag,
                "value_str": str(value),
            }
        )
    )
    app.unregister()
    app.close()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
