#!/usr/bin/env python3
"""Minimal BACnet/IP UDP adapter primitives for smoke-level integration tests."""

from __future__ import annotations

import ipaddress
import socket
import struct
from dataclasses import dataclass


# BVLC type and function codes used here.
BVLC_TYPE_BIP = 0x81
BVLC_FUNC_ORIGINAL_BROADCAST_NPDU = 0x0B
BVLC_FUNC_ORIGINAL_UNICAST_NPDU = 0x0A

# Network and APDU constants.
NPDU_VERSION = 0x01
APDU_TYPE_UNCONFIRMED_REQUEST = 0x10
UNCONFIRMED_SERVICE_WHO_IS = 0x08

# BACnet property identifier (subset).
BACNET_PROP_PRESENT_VALUE = 85

# BACnet object type numbers (subset used by profile compiler / runtime).
_OBJECT_TYPE_NAME_TO_INT: dict[str, int] = {
    "analogInput": 0,
    "analogOutput": 1,
    "analogValue": 2,
    "binaryInput": 3,
    "binaryOutput": 4,
    "binaryValue": 5,
    "multiStateValue": 19,
}


def object_type_name_to_int(name: str) -> int | None:
    key = str(name).strip()
    return _OBJECT_TYPE_NAME_TO_INT.get(key)


@dataclass(frozen=True)
class IAmFrame:
    """Parsed subset of I-Am frame metadata."""

    source_ip: str
    source_port: int
    device_instance: int


def build_who_is_frame() -> bytes:
    """Build a minimal BACnet/IP Who-Is frame (broadcast NPDU)."""
    npdu = bytes(
        [
            NPDU_VERSION,
            0x20,  # control: expecting reply
            APDU_TYPE_UNCONFIRMED_REQUEST,
            UNCONFIRMED_SERVICE_WHO_IS,
        ]
    )
    total_length = 4 + len(npdu)
    bvlc = struct.pack(">BBH", BVLC_TYPE_BIP, BVLC_FUNC_ORIGINAL_BROADCAST_NPDU, total_length)
    return bvlc + npdu


def parse_iam_frame(packet: bytes, source_ip: str, source_port: int) -> IAmFrame:
    """Parse a minimally-structured I-Am packet and extract device instance.

    This parser intentionally supports only the byte pattern used by our smoke tests:
    - BVLC (4 bytes)
    - NPDU (2 bytes)
    - APDU (2 bytes: unconfirmed + I-Am service)
    - Object ID tag (0xC4) + 4-byte object identifier
    """
    if len(packet) < 14:
        raise ValueError("packet too short for I-Am parsing")

    bvlc_type, _func, _length = struct.unpack(">BBH", packet[0:4])
    if bvlc_type != BVLC_TYPE_BIP:
        raise ValueError("unsupported BVLC type")

    obj_tag = packet[8]
    if obj_tag != 0xC4:
        raise ValueError("unexpected object identifier tag")

    object_identifier = struct.unpack(">I", packet[9:13])[0]
    object_type = (object_identifier >> 22) & 0x03FF
    if object_type != 8:  # BACnet object type: device
        raise ValueError("I-Am does not contain device object identifier")
    device_instance = object_identifier & 0x3FFFFF

    return IAmFrame(
        source_ip=source_ip,
        source_port=source_port,
        device_instance=device_instance,
    )


def build_read_property_apdu(
    object_type: int,
    object_instance: int,
    property_id: int,
    invoke_id: int = 1,
) -> bytes:
    """Build a minimal ReadProperty APDU body.

    This is a simplified APDU builder used for adapter smoke scaffolding, not a full
    BACnet encoder implementation.
    """
    if object_type < 0 or object_type > 1023:
        raise ValueError("object_type out of BACnet range")
    if object_instance < 0 or object_instance > 4194303:
        raise ValueError("object_instance out of BACnet range")
    if property_id < 0 or property_id > 4194303:
        raise ValueError("property_id out of BACnet range")
    if invoke_id < 0 or invoke_id > 255:
        raise ValueError("invoke_id out of range")

    object_identifier = (object_type << 22) | object_instance

    # PDU type: confirmed request(0x00), max-segments/max-apdu simple default.
    apdu_header = bytes([0x00, 0x05, invoke_id, 0x0C])  # 0x0C = ReadProperty service
    object_context = bytes([0x0C]) + struct.pack(">I", object_identifier)
    property_context = bytes([0x19]) + bytes([property_id & 0xFF])
    return apdu_header + object_context + property_context


class BipAdapter:
    """Minimal UDP-based BACnet/IP adapter operations for smoke integration."""

    def __init__(self, bind_host: str = "0.0.0.0", bind_port: int = 0, timeout_s: float = 1.0):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind((bind_host, bind_port))
        self._sock.settimeout(timeout_s)

    def close(self) -> None:
        self._sock.close()

    def local_address(self) -> tuple[str, int]:
        return self._sock.getsockname()

    def send_who_is(self, target_broadcast: str, port: int = 47808) -> int:
        ipaddress.ip_address(target_broadcast)  # validates format
        frame = build_who_is_frame()
        return self._sock.sendto(frame, (target_broadcast, port))

    def read_iam(self) -> IAmFrame:
        packet, (src_ip, src_port) = self._sock.recvfrom(2048)
        return parse_iam_frame(packet, src_ip, src_port)


def probe_device(
    host: str,
    port: int,
    expected_device_instance: int,
    timeout_seconds: float = 0.5,
    retries: int = 1,
) -> dict[str, object]:
    """Probe a BACnet/IP endpoint and classify result for list-first checks."""
    adapter = BipAdapter(timeout_s=timeout_seconds)
    try:
        attempts = max(1, retries)
        for _ in range(attempts):
            adapter.send_who_is(target_broadcast=host, port=port)
            try:
                iam = adapter.read_iam()
            except (TimeoutError, socket.timeout):
                continue
            if iam.device_instance != expected_device_instance:
                return {
                    "status": "identity_mismatch",
                    "host": host,
                    "port": port,
                    "device_instance": iam.device_instance,
                    "expected_device_instance": expected_device_instance,
                }
            return {
                "status": "reachable_verified",
                "host": host,
                "port": port,
                "device_instance": iam.device_instance,
                "expected_device_instance": expected_device_instance,
            }
        return {
            "status": "unreachable_timeout",
            "host": host,
            "port": port,
            "device_instance": None,
            "expected_device_instance": expected_device_instance,
        }
    finally:
        adapter.close()


def plan_write_property(
    host: str,
    port: int,
    expected_device_instance: int,
    object_type: int,
    object_instance: int,
    property_id: int,
    value: int,
    timeout_seconds: float = 0.5,
    retries: int = 1,
    *,
    dry_run: bool = True,
) -> dict[str, object]:
    """Validate reachability and (when dry_run) record an allowlisted write intent.

    Live WriteProperty over BACnet/IP is not implemented in this repository slice;
    ``dry_run=True`` returns a structured plan after a successful Who-Is/I-Am probe.
    """
    probe = probe_device(
        host=host,
        port=port,
        expected_device_instance=expected_device_instance,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    if probe.get("status") != "reachable_verified":
        return {
            "status": "blocked_probe_failed",
            "dry_run": bool(dry_run),
            "probe": probe,
            "target": {
                "object_type": object_type,
                "object_instance": object_instance,
                "property_id": property_id,
                "value": value,
            },
        }
    if not dry_run:
        return {
            "status": "use_bacpypes_client",
            "dry_run": False,
            "probe": probe,
            "target": {
                "object_type": object_type,
                "object_instance": object_instance,
                "property_id": property_id,
                "value": value,
            },
            "message": "use tools.bacnet.bacpypes_client.write_present_value for live writes",
        }
    return {
        "status": "dry_run_allowed",
        "dry_run": True,
        "probe": probe,
        "target": {
            "object_type": object_type,
            "object_instance": object_instance,
            "property_id": property_id,
            "value": value,
        },
        "note": "write_property_frame_not_sent",
    }
