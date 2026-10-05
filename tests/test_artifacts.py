"""F9 · Artifact library."""
import os
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from thesystem import artifacts


class ArtifactLibraryTests(unittest.TestCase):
    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.write("docs/artifacts/2026-10-05-overview.html", "Workspace overview")
        self.write("android-app/artifacts/2026-10-01-architecture.html", "App architecture")
        self.write("android-app/tickets/PAY-12/artifacts/2026-10-04-flow.html", "Payment flow")
        self.write("agents/artifacts/x.html", "not a project")
        (self.ws / "android-app/tickets/PAY-12/spec.md").write_text("secret spec")
        os.utime(self.ws / "android-app/artifacts/2026-10-01-architecture.html", (1, 1))

    def write(self, rel, title):
        path = self.ws / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"<html><head><title>{title}</title></head><body>{title}</body></html>")

    def test_finds_artifacts_by_project_and_ticket_newest_first(self):
        found = [(a.project, a.ticket, a.title) for a in artifacts.find_all(self.ws)]
        self.assertEqual(len(found), 3)
        self.assertIn(("", "", "Workspace overview"), found)
        self.assertIn(("android-app", "PAY-12", "Payment flow"), found)
        self.assertEqual(found[-1], ("android-app", "", "App architecture"))

    def test_only_files_inside_artifact_folders_are_served(self):
        self.assertIsNotNone(artifacts.is_servable(self.ws, "android-app/tickets/PAY-12/artifacts/2026-10-04-flow.html"))
        for rel in ("android-app/tickets/PAY-12/spec.md", "agents/artifacts/x.html",
                    "android-app/artifacts/../tickets/PAY-12/spec.md", ".git/config", ""):
            self.assertIsNone(artifacts.is_servable(self.ws, rel), rel)

    def test_server_lists_and_opens_artifacts_on_localhost(self):
        server = artifacts.serve(self.ws, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_address[1]}"
        index = urllib.request.urlopen(base + "/").read().decode()
        for text in ("Payment flow", "PAY-12", "android-app", "Workspace", "App architecture"):
            self.assertIn(text, index)
        self.assertNotIn("not a project", index)
        page = urllib.request.urlopen(base + "/android-app/tickets/PAY-12/artifacts/2026-10-04-flow.html").read()
        self.assertIn(b"Payment flow", page)
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/android-app/tickets/PAY-12/spec.md")
        self.assertEqual(error.exception.code, 404)
        self.assertEqual(server.server_address[0], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
