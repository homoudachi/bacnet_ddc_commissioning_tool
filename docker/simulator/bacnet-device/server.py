#!/usr/bin/env python3
"""UDP BACnet/IP lab device for Docker (FCU or HRV profile shapes).

Responds to Who-Is, ReadProperty (present-value), WriteProperty (present-value)
for object sets aligned with docs/examples unit-profile-fcu / unit-profile-hrv.
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


def _env_str(name: str, default: str) -> str:
    return str(os.environ.get(name, default)).strip().lower()


DEVICE_INSTANCE = _env_int("DEVICE_INSTANCE", 21001)
UDP_PORT = _env_int("BACNET_UDP_PORT", 47808)
SIM_PROFILE = _env_str("SIM_PROFILE", "fcu")


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
        # COV subscriptions: (subscriber IPv4, subscriber UDP port) -> {process_id: mon_ot}
        self._cov_by_addr: dict[tuple[str, int], dict[int, tuple[int, int]]] = {}
        self.profile = SIM_PROFILE
        if self.profile == "hrv":
            self.msv_present = _env_int("SIM_MSV_TEST_MODE", 1)
            self.bi_fan_active = _env_int("SIM_BI_FAN_ACTIVE", 0) != 0
            self.ai_oa = _env_float("SIM_AI_OA_TEMP", 10.0)
            self.ai_supply = _env_float("SIM_AI_SUPPLY_TEMP", 20.0)
            self.ai_exhaust = _env_float("SIM_AI_EXHAUST_TEMP", 19.0)
            self.av_supply_cmd = _env_float("SIM_AV_SUPPLY_FAN", 50.0)
            self.av_exhaust_cmd = _env_float("SIM_AV_EXHAUST_FAN", 50.0)
        else:
            self.ai_present = _env_float("SIM_AI_SAT", 21.5)
            self.msv_present = _env_int("SIM_MSV_TEST_MODE", 1)
            self.av_heat = _env_float("SIM_AV_HEAT", 0.0)
            self.ao_valve = _env_float("SIM_AO_CHW_VALVE", 0.0)

    def _cov_sub_key(self, addr: tuple[str, int]) -> tuple[str, int]:
        return (addr[0], int(addr[1]))

    def _cov_store(
        self,
        addr: tuple[str, int],
        process_id: int,
        monitored_ot: int,
        monitored_oi: int,
    ) -> None:
        key = self._cov_sub_key(addr)
        with self._lock:
            bucket = self._cov_by_addr.setdefault(key, {})
            bucket[int(process_id)] = (int(monitored_ot), int(monitored_oi))

    def _cov_remove(self, addr: tuple[str, int], process_id: int) -> None:
        key = self._cov_sub_key(addr)
        with self._lock:
            bucket = self._cov_by_addr.get(key)
            if not bucket:
                return
            bucket.pop(int(process_id), None)
            if not bucket:
                self._cov_by_addr.pop(key, None)

    def _send_unconfirmed_cov(
        self,
        sock: socket.socket,
        addr: tuple[str, int],
        *,
        process_id: int,
        monitored_ot: int,
        monitored_oi: int,
        present_value: float | int,
        time_remaining: int = 60,
    ) -> None:
        from bacpypes3.apdu import UnconfirmedCOVNotificationRequest
        from bacpypes3.basetypes import PropertyIdentifier, PropertyValue
        from bacpypes3.constructeddata import Any, SequenceOf
        from bacpypes3.primitivedata import ObjectIdentifier, Real, Unsigned
        from bacpypes3.pdu import IPv4Address

        pv = float(present_value) if isinstance(present_value, (int, float)) else float(present_value)
        pv_any = Any(Real(pv))
        prop_val = PropertyValue(
            propertyIdentifier=PropertyIdentifier("present-value"),
            value=pv_any,
        )
        note = UnconfirmedCOVNotificationRequest(
            subscriberProcessIdentifier=Unsigned(int(process_id)),
            initiatingDeviceIdentifier=ObjectIdentifier(("device", DEVICE_INSTANCE)),
            monitoredObjectIdentifier=ObjectIdentifier((monitored_ot, monitored_oi)),
            timeRemaining=Unsigned(int(time_remaining)),
            listOfValues=SequenceOf(PropertyValue)([prop_val]),
            destination=IPv4Address(f"{addr[0]}:{addr[1]}"),
        )
        apdu_wire = note.encode().encode().pduData
        sock.sendto(_bvlc_original_unicast(b"\x01\x00" + apdu_wire), addr)

    def _notify_cov_present_value(
        self,
        sock: socket.socket,
        ot: int,
        oi: int,
        present_value: float | int,
    ) -> None:
        """Fan-out unconfirmed COV notifications for present-value changes."""
        with self._lock:
            subs_snapshot = {
                addr_key: dict(bucket)
                for addr_key, bucket in self._cov_by_addr.items()
            }
        for (ip, port), by_proc in subs_snapshot.items():
            for proc_id, (mot, moi) in by_proc.items():
                if mot == ot and moi == oi:
                    try:
                        self._send_unconfirmed_cov(
                            sock,
                            (ip, port),
                            process_id=proc_id,
                            monitored_ot=mot,
                            monitored_oi=moi,
                            present_value=present_value,
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"cov_notify_error: {exc!r}", flush=True)

    def handle(self, sock: socket.socket, addr: tuple[str, int], apdu_bytes: bytes) -> None:
        from bacpypes3.apdu import (
            APDU,
            ConfirmedRequestPDU,
            ConfirmedServiceChoice,
            IAmRequest,
            ReadPropertyACK,
            ReadPropertyRequest,
            SimpleAckPDU,
            SubscribeCOVRequest,
            UnconfirmedRequestPDU,
            UnconfirmedServiceChoice,
            WritePropertyMultipleRequest,
            WritePropertyRequest,
        )
        from bacpypes3.basetypes import Segmentation
        from bacpypes3.constructeddata import Any
        from bacpypes3.primitivedata import Boolean, ObjectIdentifier, Real, Unsigned
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
        if svc == int(ConfirmedServiceChoice.subscribeCOV):
            req = SubscribeCOVRequest.decode(inc)
            proc_id = int(req.subscriberProcessIdentifier)
            obj_id = req.monitoredObjectIdentifier
            mon_ot, mon_oi = int(obj_id[0]), int(obj_id[1])
            cancel = req.issueConfirmedNotifications is None and req.lifetime is None
            if cancel:
                self._cov_remove(addr, proc_id)
                sack = SimpleAckPDU(
                    service_choice=ConfirmedServiceChoice.subscribeCOV, context=inc
                )
                wire = sack.encode().pduData
                sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)
                return
            self._cov_store(addr, proc_id, mon_ot, mon_oi)
            sack = SimpleAckPDU(
                service_choice=ConfirmedServiceChoice.subscribeCOV, context=inc
            )
            wire = sack.encode().pduData
            sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)
            # Initial notification (matches common device behavior; helps tests).
            if self.profile == "hrv":
                if mon_ot == 0 and mon_oi == 15:
                    with self._lock:
                        pv = float(self.ai_supply)
                    self._notify_cov_present_value(sock, mon_ot, mon_oi, pv)
            else:
                if mon_ot == 0 and mon_oi == 2:
                    with self._lock:
                        pv = float(self.ai_present)
                    self._notify_cov_present_value(sock, mon_ot, mon_oi, pv)
            return

        if svc == int(ConfirmedServiceChoice.readProperty):
            req = ReadPropertyRequest.decode(inc)
            if str(req.propertyIdentifier) != "present-value":
                return
            ot = int(req.objectIdentifier[0])
            oi = int(req.objectIdentifier[1])
            payload = self._read_payload(ot, oi)
            if payload is None:
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

        if svc == int(ConfirmedServiceChoice.writePropertyMultiple):
            mreq = WritePropertyMultipleRequest.decode(inc)
            all_ok = True
            for spec in mreq.listOfWriteAccessSpecs:
                oid = spec.objectIdentifier
                ot_w = int(oid[0])
                oi_w = int(oid[1])
                for pv in spec.listOfProperties:
                    if str(pv.propertyIdentifier) != "present-value":
                        continue
                    if not self._apply_write(ot_w, oi_w, pv.value):
                        all_ok = False
                        break
                    if self.profile == "hrv":
                        if ot_w == 0 and oi_w == 15:
                            with self._lock:
                                supv = float(self.ai_supply)
                            self._notify_cov_present_value(sock, ot_w, oi_w, supv)
                    else:
                        if ot_w == 0 and oi_w == 2:
                            with self._lock:
                                aipv = float(self.ai_present)
                            self._notify_cov_present_value(sock, ot_w, oi_w, aipv)
                if not all_ok:
                    break
            if not all_ok:
                return
            sack = SimpleAckPDU(
                service_choice=ConfirmedServiceChoice.writePropertyMultiple, context=inc
            )
            wire = sack.encode().pduData
            sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)
            return

        if svc == int(ConfirmedServiceChoice.writeProperty):
            wreq = WritePropertyRequest.decode(inc)
            if str(wreq.propertyIdentifier) != "present-value":
                return
            ot_w = int(wreq.objectIdentifier[0])
            oi_w = int(wreq.objectIdentifier[1])
            if not self._apply_write(ot_w, oi_w, wreq.propertyValue):
                return
            if self.profile == "hrv":
                if ot_w == 0 and oi_w == 15:
                    with self._lock:
                        pv = float(self.ai_supply)
                    self._notify_cov_present_value(sock, ot_w, oi_w, pv)
            else:
                if ot_w == 0 and oi_w == 2:
                    with self._lock:
                        pv = float(self.ai_present)
                    self._notify_cov_present_value(sock, ot_w, oi_w, pv)
            sack = SimpleAckPDU(service_choice=ConfirmedServiceChoice.writeProperty, context=inc)
            wire = sack.encode().pduData
            sock.sendto(_bvlc_original_unicast(b"\x01\x00" + wire), addr)
            return

    def _read_payload(self, ot: int, oi: int):
        from bacpypes3.constructeddata import Any
        from bacpypes3.primitivedata import Boolean, Real, Unsigned

        if self.profile == "hrv":
            with self._lock:
                msv = self.msv_present
                bi_act = self.bi_fan_active
                oa = self.ai_oa
                sup = self.ai_supply
                exh = self.ai_exhaust
                sc = self.av_supply_cmd
                ec = self.av_exhaust_cmd
            if ot == 19 and oi == 60:
                return Any(Unsigned(msv))
            if ot == 3 and oi == 9:
                return Any(Boolean(bool(bi_act)))
            if ot == 0 and oi == 14:
                return Any(Real(oa))
            if ot == 0 and oi == 15:
                return Any(Real(sup))
            if ot == 0 and oi == 16:
                return Any(Real(exh))
            if ot == 2 and oi == 12:
                return Any(Real(sc))
            if ot == 2 and oi == 13:
                return Any(Real(ec))
            return None

        with self._lock:
            ai_val = self.ai_present
            msv_val = self.msv_present
            av_heat = self.av_heat
            ao_valve = self.ao_valve
        if ot == 0 and oi == 2:
            return Any(Real(ai_val))
        if ot == 19 and oi == 50:
            return Any(Unsigned(msv_val))
        if ot == 2 and oi == 3:
            return Any(Real(av_heat))
        if ot == 2 and oi == 4:
            return Any(Real(av_heat))
        if ot == 1 and oi == 5:
            return Any(Real(ao_valve))
        return None

    def _apply_write(self, ot_w: int, oi_w: int, prop_value) -> bool:
        from bacpypes3.primitivedata import Real, Unsigned

        if self.profile == "hrv":
            if ot_w == 19 and oi_w == 60:
                new_val = int(prop_value.cast_out(Unsigned))
                with self._lock:
                    self.msv_present = new_val
                return True
            if ot_w == 2 and oi_w == 12:
                new_val = float(prop_value.cast_out(Real))
                with self._lock:
                    self.av_supply_cmd = new_val
                return True
            if ot_w == 2 and oi_w == 13:
                new_val = float(prop_value.cast_out(Real))
                with self._lock:
                    self.av_exhaust_cmd = new_val
                return True
            return False


        if ot_w == 19 and oi_w == 50:
            new_val = int(prop_value.cast_out(Unsigned))
            with self._lock:
                self.msv_present = new_val
            return True
        if ot_w == 2 and oi_w == 3:
            new_val = float(prop_value.cast_out(Real))
            with self._lock:
                self.av_heat = new_val
            return True
        if ot_w == 2 and oi_w == 4:
            new_val = float(prop_value.cast_out(Real))
            with self._lock:
                self.av_heat = new_val
            return True
        if ot_w == 1 and oi_w == 5:
            new_val = float(prop_value.cast_out(Real))
            with self._lock:
                self.ao_valve = new_val
            return True
        return False


def main() -> None:
    state = BacnetSimState()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", UDP_PORT))
    print(
        f"bacnet_sim_device profile={state.profile} udp=0.0.0.0:{UDP_PORT} "
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
