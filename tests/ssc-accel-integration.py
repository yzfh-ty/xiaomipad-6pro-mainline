#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run iio-sensor-proxy's upstream SSC fixture with liuqin admission."""

import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {sys.argv[0]} UPSTREAM_SSC_TEST")

    test_path = pathlib.Path(sys.argv[1])
    spec = importlib.util.spec_from_file_location(
        "iio_sensor_proxy_ssc_test", test_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load upstream test: {test_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    upstream_test = module.Tests.test_ssc_accel
    if not getattr(upstream_test, "__unittest_skip__", False):
        raise RuntimeError("upstream SSC accelerometer test contract changed")

    class LiuqinSSCTests(module.Tests):
        def require_mock_transport(self):
            """Report the real QRTR error inside the exact UMockdev testbed."""
            probe = os.environ.get("LIUQIN_QRTR_PROBE")
            if not probe:
                raise RuntimeError("LIUQIN_QRTR_PROBE must name the built transport probe")
            env = os.environ.copy()
            env["UMOCKDEV_DIR"] = self.testbed.get_root_dir()
            result = subprocess.run(
                [probe, "--ssc"], env=env, capture_output=True, text=True, timeout=10
            )
            self.assertEqual(
                result.returncode, 0,
                "QRTR transport failed inside UMockdev:\n" + result.stdout + result.stderr,
            )

        def start_daemon_before_coldplug_finishes(self):
            """Own the proxy as soon as its bus name appears, before SSC discovery."""
            env = os.environ.copy()
            env["G_DEBUG"] = "fatal-criticals"
            env["G_MESSAGES_DEBUG"] = "all"
            env["UMOCKDEV_DEBUG"] = "all"
            env["UMOCKDEV_DIR"] = self.testbed.get_root_dir()
            self.log = tempfile.NamedTemporaryFile()
            self.daemon = subprocess.Popen(
                [self.daemon_path, "-v"],
                env=env,
                stdout=self.log,
                stderr=subprocess.STDOUT,
            )

            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                proxy = module.Gio.DBusProxy.new_sync(
                    self.dbus,
                    module.Gio.DBusProxyFlags.DO_NOT_AUTO_START,
                    None,
                    module.SP,
                    module.SP_PATH,
                    module.SP,
                    None,
                )
                if proxy.get_name_owner() is not None:
                    self.proxy = proxy
                    break
                time.sleep(0.02)
            else:
                self.fail("SensorProxy did not own its D-Bus name in 10 seconds")

            self.assertEqual(self.daemon.poll(), None, "daemon crashed")

        @staticmethod
        def add_liuqin_accelerometer(testbed):
            testbed.add_device(
                "misc",
                "ssc-accel",
                None,
                ["name", "SSC Test Accelerometer Sensor"],
                [
                    "NAME",
                    '"SSC Accelerometer Sensor"',
                    "DEVNAME",
                    "/dev/fastrpc-sdsp",
                    "IIO_SENSOR_PROXY_TYPE",
                    "ssc-accel",
                ],
            )

        def test_liuqin_ssc_accel(self):
            self.add_liuqin_accelerometer(self.testbed)
            self.require_mock_transport()
            self.start_daemon()
            self.assertEqual(self.get_dbus_property("HasAmbientLight"), False)
            self.assertEventually(
                lambda: bool(self.get_dbus_property("HasAccelerometer"))
            )
            self.assertEqual(self.get_dbus_property("HasProximity"), False)
            self.assertEqual(
                self.get_compass_dbus_property("HasCompass"), False
            )
            self.assertEventually(
                lambda: self.get_dbus_property("AccelerometerOrientation")
                == "undefined"
            )
            self.proxy.ClaimAccelerometer()
            self.assertEventually(
                lambda: self.get_dbus_property("AccelerometerOrientation")
                == "left-up"
            )
            self.stop_daemon()

        def test_liuqin_ssc_claim_during_coldplug(self):
            self.add_liuqin_accelerometer(self.testbed)
            self.require_mock_transport()
            self.start_daemon_before_coldplug_finishes()

            self.assertEqual(self.get_dbus_property("HasAccelerometer"), False)
            self.proxy.ClaimAccelerometer()
            self.assertEventually(
                lambda: self.get_dbus_property("AccelerometerOrientation")
                == "left-up",
                timeout=300,
            )
            self.assertEqual(self.get_dbus_property("HasAccelerometer"), True)

            with open(self.log.name, encoding="utf-8") as daemon_log:
                output = daemon_log.read()
            claim = output.find(
                "Handling driver refcounting method 'ClaimAccelerometer'"
            )
            discovered = output.find("Found device ")
            self.assertGreaterEqual(claim, 0)
            self.assertGreater(discovered, claim)
            self.assertEqual(output.count("Enabling sensor ("), 1)
            self.stop_daemon()

    suite = unittest.TestSuite(
        (
            LiuqinSSCTests("test_liuqin_ssc_accel"),
            LiuqinSSCTests("test_liuqin_ssc_claim_during_coldplug"),
        )
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() and result.testsRun == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
