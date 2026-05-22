import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tests._path  # noqa: F401
from ga_reporter.credentials import resolve_service_account_path


SERVICE_ACCOUNT_PAYLOAD = {
    "type": "service_account",
    "project_id": "demo-project",
    "private_key_id": "key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
    "client_email": "demo@example.com",
}


class SecretMapping(dict):
    def to_dict(self):
        return dict(self)


class TestCredentials(unittest.TestCase):
    def test_resolve_from_environment(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": "C:\\secret.json"}, clear=True):
            path, source = resolve_service_account_path(repo_root=Path.cwd(), streamlit_secrets=None)
        self.assertEqual(path, "C:\\secret.json")
        self.assertEqual(source, "environment variable")

    def test_resolve_from_streamlit_secret_path(self) -> None:
        path, source = resolve_service_account_path(
            repo_root=Path.cwd(),
            streamlit_secrets={"google_service_account_path": "C:\\secure\\sa.json"},
        )
        self.assertEqual(path, "C:\\secure\\sa.json")
        self.assertEqual(source, "streamlit secrets path")

    def test_resolve_from_streamlit_secret_payload(self) -> None:
        path, source = resolve_service_account_path(
            repo_root=Path.cwd(),
            streamlit_secrets={"google_service_account": SecretMapping(SERVICE_ACCOUNT_PAYLOAD)},
        )
        self.assertTrue(path is not None)
        self.assertEqual(source, "streamlit secrets payload")
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        self.assertEqual(payload["type"], "service_account")

    def test_resolve_from_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            file_path = repo_root / "service_account.json"
            file_path.write_text(json.dumps(SERVICE_ACCOUNT_PAYLOAD), encoding="utf-8")
            path, source = resolve_service_account_path(repo_root=repo_root, streamlit_secrets=None)
        self.assertEqual(path, str(file_path))
        self.assertEqual(source, "local ignored file")


if __name__ == "__main__":
    unittest.main()
