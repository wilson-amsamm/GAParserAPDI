import json
import tempfile
import unittest
from pathlib import Path

import tests._path  # noqa: F401
from ga_reporter.config import load_property_config


class TestConfig(unittest.TestCase):
    def test_load_valid_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "properties.json"
            config_path.write_text(
                json.dumps(
                    {
                        "properties": [
                            {"site_name": "Site A", "property_id": "111"},
                            {"site_name": "Site B", "property_id": "222"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            properties = load_property_config(str(config_path))
            self.assertEqual(len(properties), 2)
            self.assertEqual(properties[0].site_name, "Site A")
            self.assertEqual(properties[1].property_id, "222")

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_property_config("config/does-not-exist.json")

    def test_invalid_properties_shape_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "bad.json"
            config_path.write_text(json.dumps({"properties": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_property_config(str(config_path))


if __name__ == "__main__":
    unittest.main()
