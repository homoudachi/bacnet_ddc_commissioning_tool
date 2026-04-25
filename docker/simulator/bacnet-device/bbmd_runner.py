#!/usr/bin/env python3
"""Minimal BACnet/IP BBMD for lab compose (BACpypes3 BBMDApplication).

Binds UDP on BACNET_BBMD_PORT (default 47830). Optional BDT peers from
BACNET_BDT_BROADCAST_PEERS: comma-separated ``host:port`` directed-broadcast
targets (one per remote subnet) used with ``BBMDApplication.add_peer``.
"""

from __future__ import annotations

import asyncio
import os
import sys


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_peer_list(raw: str) -> list[str]:
    out: list[str] = []
    for part in str(raw or "").split(","):
        p = part.strip()
        if p:
            out.append(p)
    return out


async def _amain() -> None:
    from bacpypes3.basetypes import Segmentation
    from bacpypes3.local.device import DeviceObject
    from bacpypes3.primitivedata import CharacterString, ObjectIdentifier, Unsigned
    from bacpypes3.pdu import IPv4Address
    from bacpypes3.ipv4.app import BBMDApplication

    port = _env_int("BACNET_BBMD_PORT", 47830)
    dev_inst = _env_int("BBMD_DEVICE_INSTANCE", 111000)
    bind_addr = os.environ.get("BACNET_BBMD_BIND", f"0.0.0.0:{port}").strip()

    device = DeviceObject(
        objectIdentifier=ObjectIdentifier(("device", dev_inst)),
        objectName=CharacterString("bacnet-lab-bbmd"),
        maxAPDULengthAccepted=Unsigned(1476),
        segmentationSupported=Segmentation("noSegmentation"),
        vendorID=Unsigned(0),
    )
    app = BBMDApplication(device, IPv4Address(bind_addr))
    for peer in _parse_peer_list(os.environ.get("BACNET_BDT_BROADCAST_PEERS", "")):
        app.add_peer(IPv4Address(peer))
    print(
        f"bacnet_bbmd bind={bind_addr} device_instance={dev_inst} "
        f"bdt_peers={_parse_peer_list(os.environ.get('BACNET_BDT_BROADCAST_PEERS', ''))}",
        flush=True,
    )
    # Run until stopped (Docker CMD); BBMD stack services UDP on the bound port.
    await asyncio.Event().wait()


def main() -> None:
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
