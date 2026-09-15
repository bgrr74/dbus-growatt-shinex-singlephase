import unittest

from growatt_shinex import parse_measurement


class ParseMeasurementTests(unittest.TestCase):
    def test_running_single_phase_inverter(self):
        result = parse_measurement(
            {
                "Mac": "AA:BB:CC:DD:EE:FF",
                "InverterStatus": 1,
                "OutputPower": 1234.5,
                "L1ThreePhaseGridOutputPower": 1200.0,
                "L1ThreePhaseGridVoltage": 230.5,
                "L1ThreePhaseGridOutputCurrent": 5.4,
                "TotalGenerateEnergy": 4567.89,
                "ErrorCode": 0,
            }
        )

        self.assertEqual(result.serial, "AABBCCDDEEFF")
        self.assertTrue(result.inverter_running)
        self.assertEqual(result.power, 1234.5)
        self.assertEqual(result.voltage, 230.5)
        self.assertEqual(result.current, 5.4)
        self.assertEqual(result.energy, 4567.89)

    def test_reachable_but_sleeping_inverter_has_zero_power(self):
        result = parse_measurement(
            {
                "InverterStatus": 0,
                "OutputPower": 12,
                "L1ThreePhaseGridVoltage": 231,
                "L1ThreePhaseGridOutputCurrent": 0.1,
                "TotalGenerateEnergy": 100,
            }
        )

        self.assertFalse(result.inverter_running)
        self.assertEqual(result.power, 0)
        self.assertEqual(result.current, 0)
        self.assertEqual(result.voltage, 231)
        self.assertEqual(result.energy, 100)

    def test_l1_power_fallback_and_calculated_current(self):
        result = parse_measurement(
            {
                "InverterStatus": "running",
                "L1ThreePhaseGridOutputPower": 115,
                "L1ThreePhaseGridVoltage": 230,
                "L1ThreePhaseGridOutputCurrent": 0,
            }
        )

        self.assertEqual(result.power, 115)
        self.assertAlmostEqual(result.current, 0.5)
        self.assertIsNone(result.energy)

    def test_invalid_values_are_safe(self):
        result = parse_measurement(
            {
                "InverterStatus": 1,
                "OutputPower": "not-a-number",
                "L1ThreePhaseGridVoltage": -1,
                "L1ThreePhaseGridOutputCurrent": None,
                "TotalGenerateEnergy": "nan",
                "ErrorCode": "invalid",
            }
        )

        self.assertEqual(result.power, 0)
        self.assertEqual(result.voltage, 0)
        self.assertEqual(result.current, 0)
        self.assertIsNone(result.energy)
        self.assertEqual(result.error_code, 0)

    def test_non_object_response_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_measurement([])

    def test_json_without_inverter_fields_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_measurement({"message": "not ready"})

    def test_three_real_single_phase_payload_shapes(self):
        samples = (
            (
                {
                    "InverterStatus": 1,
                    "OutputPower": 1727.5,
                    "L1ThreePhaseGridVoltage": 242.6,
                    "L1ThreePhaseGridOutputCurrent": 7.2,
                    "L1ThreePhaseGridOutputPower": 1727.8,
                    "TotalGenerateEnergy": 14391.6,
                },
                (1727.5, 242.6, 7.2, 14391.6),
            ),
            (
                {
                    "InverterStatus": 1,
                    "OutputPower": 227.1,
                    "L1ThreePhaseGridVoltage": 239.7,
                    "L1ThreePhaseGridOutputCurrent": 0.9,
                    "L1ThreePhaseGridOutputPower": 224.4,
                    "TotalGenerateEnergy": 7724.9,
                },
                (227.1, 239.7, 0.9, 7724.9),
            ),
            (
                {
                    "InverterStatus": 1,
                    "OutputPower": 2775.4,
                    "L1ThreePhaseGridVoltage": 243.9,
                    "L1ThreePhaseGridOutputCurrent": 11.2,
                    "L1ThreePhaseGridOutputPower": 2777.4,
                    "TotalGenerateEnergy": 8553.7,
                },
                (2775.4, 243.9, 11.2, 8553.7),
            ),
        )

        for payload, expected in samples:
            with self.subTest(output_power=payload["OutputPower"]):
                result = parse_measurement(payload)
                self.assertEqual(
                    (result.power, result.voltage, result.current, result.energy),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
