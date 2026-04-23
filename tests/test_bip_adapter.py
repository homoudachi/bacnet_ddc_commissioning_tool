import socket
import threading
import time
import unittest

from tools.bacnet import bip_adapter


def _build_i_am_packet(device_instance: int) -> bytes:
    """Build a minimal BACnet/IP I-Am frame for tests."""
    object_identifier = (8 << 22) | (device_instance & 0x3FFFFF)
    apdu = b"\x10\x00\xc4" + object_identifier.to_bytes(4, "big") + b"\x22\x00\x91\x00"
    npdu = b"\x01\x00"
    payload = npdu + apdu
    bvlc = b"\x81\x0a" + (len(payload) + 4).to_bytes(2, "big")
    return bvlc + payload


class _FakeBipServer:
    def __init__(self, device_instance: int, respond: bool = True) -> None:
        self.device_instance = device_instance
        self.respond = respond
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = 0
        self.last_packet: bytes | None = None

    def start(self) -> None:
        self._thread.start()
        if not self._ready.wait(timeout=2):
            raise RuntimeError("fake server failed to start")

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.1)
            self.port = sock.getsockname()[1]
            self._ready.set()
            while not self._stop.is_set():
                try:
                    data, addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                self.last_packet = data
                if self.respond:
                    sock.sendto(_build_i_am_packet(self.device_instance), addr)
        finally:
            sock.close()


class BipAdapterTests(unittest.TestCase):
    def test_probe_device_returns_reachable_verified_for_matching_instance(self) -> None:
        server = _FakeBipServer(device_instance=21001, respond=True)
        server.start()
        try:
            result = bip_adapter.probe_device(
                host="127.0.0.1",
                port=server.port,
                expected_device_instance=21001,
                timeout_seconds=0.5,
                retries=1,
            )
        finally:
            server.stop()

        self.assertEqual("reachable_verified", result["status"])
        self.assertEqual(21001, result["device_instance"])
        self.assertIsNotNone(server.last_packet)
        self.assertTrue(server.last_packet.startswith(b"\x81"))

    def test_probe_device_returns_identity_mismatch_for_wrong_instance(self) -> None:
        server = _FakeBipServer(device_instance=22002, respond=True)
        server.start()
        try:
            result = bip_adapter.probe_device(
                host="127.0.0.1",
                port=server.port,
                expected_device_instance=21001,
                timeout_seconds=0.5,
                retries=1,
            )
        finally:
            server.stop()

        self.assertEqual("identity_mismatch", result["status"])
        self.assertEqual(22002, result["device_instance"])

    def test_probe_device_returns_timeout_when_no_i_am_response(self) -> None:
        server = _FakeBipServer(device_instance=21001, respond=False)
        server.start()
        try:
            start = time.time()
            result = bip_adapter.probe_device(
                host="127.0.0.1",
                port=server.port,
                expected_device_instance=21001,
                timeout_seconds=0.2,
                retries=1,
            )
            elapsed = time.time() - start
        finally:
            server.stop()

        self.assertEqual("unreachable_timeout", result["status"])
        self.assertGreaterEqual(elapsed, 0.15)
