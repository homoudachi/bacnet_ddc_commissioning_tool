#!/usr/bin/env python3
"""UDP BACnet/IP loopback-style device for Docker (FCU-style objects).

Responds to Who-Is, ReadProperty (present-value), WriteProperty (present-value)
for a small fixed object set matching docs/examples FCU profile instances.
"""

from __future__ import annotations

import os
import socket
import threading


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


DEVICE_INSTANCE = _env_int("DEVICE_INSTANCE", 21001)
UDP_PORT = _env_int("BACNET_UDP_PORT", 47808)


def _bvlc_original_unicast(npdu_and_apdu: bytes) -> bytes:
    total = 4 + len(npdu_and_apdu)
    return b"\x81\x0a" + total.to_bytes(2, "big") + npdu_and_apdu


def _extract_apdu(data: bytes) -> bytes | None:
    if len(data) < 4 or data[0] != 0x81 or data[1] not in (0x0A, 0x0B):
        return None
    length = int.from_bytes(data[2:4], "big")
    if length > len(data) or length < 4 + 2:
        return None
    inner = data[4:length]
    if len(inner) < 2:
        return None
    return inner[2:]


class BacnetSimState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.ai_present = _env_float("SIM_AI_SAT", 21.5)
        self.msv_present = _env_int("SIM_MSV_TEST_MODE", 1)
        self.av_heat = _env_float("SIM_AV_HEAT", 0.0)
        self.ao_valve = _env_float("SIM_AO_CHW_VALVE", 0.0)

    def handle(self, sock: socket.socket, addr: tuple[str, int], apdu_bytes: bytes) -> None:
        from bacpypes3.apdu import (
            APDU,
            ConfirmedRequestPDU,
            ConfirmedServiceChoice,
            IAmRequest,
            ReadPropertyACK,
            ReadPropertyRequest,
            SimpleAckPDU,
            UnconfirmedRequestPDU,
            UnconfirmedServiceChoice,
            WritePropertyRequest,
        )
        from bacpypes3.basetypes import PropertyIdentifier, Segmentation
        from bacpypes3.constructeddata import Any
        from bacpypes3.primitivedata import ObjectIdentifier, Real, Unsigned
        from bacpypes3.pdu import IPv4Address, PDU

        src = IPv4Address(f"{addr[0]}:{addr[1]}")
        inc = APDU.decode(PDU(apdu_bytes))
        inc.pduSource = src

        if isinstance(inc, UnconfirmedRequestPDU):
            if int(inc.apduService) == int(UnconfirmedServiceChoice.whoIs):
                iam = IAmRequest(
                    iAmDeviceIdentifier=ObjectIdentifier(("device", DEVICE_INSTANCE)),
                    maxAPDULengthAccepted=Unsigned(1476),
                    segmentationSupported=Segmentation("noSegmentation"),
                    vendorID=Unsigned(0),
                    destination=src,
                )
                apdu_wire = iam.encode().encode().pduData
                sock.sendto(_bvlc_original_unicast(b"\x01\x00" + apdu_wire), addr)
            return

        if not isinstance(inc, ConfirmedRequestPDU):
            return

        svc = int(inc.apduService)
        if svc == int(ConfirmedServiceChoice.readProperty):
            req = ReadPropertyRequest.decode(inc)
            if str(req.propertyIdentifier) != "present-value":
                return
            ot = int(req.objectIdentifier[0])
            oi = int(req.objectIdentifier[1])
            with self._lock:
                ai_val = self.ai_present
                msv_val = self.msv_present
                av_heat = self.av_heat
                ao_valve = self.ao_valve
            if ot == 0 and oi == 2:
                payload = Any(Real(ai_val))
            elif ot == 19 and oi == 50:
                payload = Any(Unsigned(msv_val))
            elif ot == 2 and oi == 3:
                payload = Any(Real(av_heat))
            elif ot == 2 and oi == 4:
                payload = Any(Real(av_heat))
            elif ot == 1 and oi == 5:
                payload = Any(Real(ao_valve))
            else:
                return
            ack = ReadPropertyACK(
                objectIdentifier=req.objectIdentifier,
                propertyIdentifier=req.propertyIdentifier,
                propertyValue=payload,
            )
            inner = ack.encode()
            inner.apduInvokeID = inc.apduInvokeID
            inner.apduSeg = 0
            inner.apduMor = 0
            inner.set_context(inc)
            wire = inner.encode().pduData
            sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)
            return

        if svc == int(ConfirmedServiceChoice.writeProperty):
            wreq = WritePropertyRequest.decode(inc)
            if str(wreq.propertyIdentifier) != "present-value":
                return
            ot_w = int(wreq.objectIdentifier[0])
            oi_w = int(wreq.objectIdentifier[1])
            if ot_w == 19 and oi_w == 50:
                new_val = int(wreq.propertyValue.cast_out(Unsigned))
                with self._lock:
                    self.msv_present = new_val
            elif ot_w == 2 and oi_w == 3:
                new_val = float(wreq.propertyValue.cast_out(Real))
                with self._lock:
                    self.av_heat = new_val
            elif ot_w == 2 and oi_w == 4:
                new_val = float(wreq.propertyValue.cast_out(Real))
                with self._lock:
                    self.av_heat = new_val
            elif ot_w == 1 and oi_w == 5:
                new_val = float(wreq.propertyValue.cast_out(Real))
                with self._lock:
                    self.ao_valve = new_val
            else:
                return
            sack = SimpleAckPDU(service_choice=ConfirmedServiceChoice.writeProperty, context=inc)
            wire = sack.encode().pduData
            sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)


def main() -> None:
    state = BacnetSimState()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(
        f"bacnet_sim_device listening udp=0.0.0.0:{UDP_PORT} "
        f"device_instance={DEVICE_INSTANCE}",
        flush=True,
    )
    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except OSError:
            break
        apdu = _extract_apdu(data)
        if apdu is None:
            continue
        try:
            state.handle(sock, addr, apdu)
        except Exception as exc:  # noqa: BLE001
            print(f"handler_error: {exc!r}", flush=True)


if __name__ == "__main__":
    main()
