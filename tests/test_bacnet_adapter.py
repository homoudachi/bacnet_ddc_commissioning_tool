import importlib.util
import pathlib
import unittest
from unittest.mock import MagicMock


ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTER_PATH = ROOT / "tools" / "bacnet" / "adapter.py"


def _load_adapter_module():
    spec = importlib.util.spec_from_file_location("bacnet_adapter_test_mod", ADAPTER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("adapter spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class BacnetAdapterTests(unittest.TestCase):
    def test_format_target_and_present_value_property_id(self) -> None:
        mod = _load_adapter_module()
        adapter = mod.CommissioningBACnetAdapter(ROOT)
        self.assertEqual(85, adapter.present_value_property_id)
        self.assertEqual("192.168.1.10:47808", adapter.format_ipv4_target("192.168.1.10", 47808))
        self.assertEqual(0, adapter.object_type_name_to_int("analogInput"))
        self.assertIsNone(adapter.object_type_name_to_int("unknownType"))

    def test_read_present_value_delegates_to_client_module(self) -> None:
        mod = _load_adapter_module()
        adapter = mod.CommissioningBACnetAdapter(ROOT)
        mock_client = MagicMock()
        mock_client.read_present_value.return_value = {"status": "read_ok", "value_str": "1"}
        adapter._client_mod = mock_client
        result = adapter.read_present_value(
            bind_port=0,
            target_address="127.0.0.1:12345",
            expected_device_instance=1,
            object_type=19,
            object_instance=50,
            property_name="presentValue",
            who_is_timeout=1.0,
            apdu_timeout=2.0,
        )
        self.assertEqual("read_ok", result["status"])
        mock_client.read_present_value.assert_called_once_with(
            bind_port=0,
            target_address="127.0.0.1:12345",
            expected_device_instance=1,
            object_type=19,
            object_instance=50,
            property_name="presentValue",
            who_is_timeout=1.0,
            apdu_timeout=2.0,
        )

    def test_probe_device_delegates_to_bip_module(self) -> None:
        mod = _load_adapter_module()
        adapter = mod.CommissioningBACnetAdapter(ROOT)
        mock_bip = MagicMock()
        mock_bip.probe_device.return_value = {"status": "reachable_verified"}
        adapter._bip_mod = mock_bip
        out = adapter.probe_device(
            host="10.0.0.1",
            port=47808,
            expected_device_instance=21001,
            timeout_seconds=0.5,
            retries=2,
        )
        self.assertEqual("reachable_verified", out["status"])
        mock_bip.probe_device.assert_called_once_with(
            host="10.0.0.1",
            port=47808,
            expected_device_instance=21001,
            timeout_seconds=0.5,
            retries=2,
        )
