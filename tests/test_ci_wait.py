import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import ci_wait  # noqa: E402

T0 = 1_700_000_000  # fake epoch


def iso(offset):
    import datetime
    return datetime.datetime.fromtimestamp(
        T0 + offset, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def job(name, status="completed", conclusion="success", steps=None,
        start=0, end=120):
    return {"name": name, "status": status, "conclusion": conclusion,
            "started_at": iso(start), "completed_at": iso(end) if end else None,
            "steps": steps or []}


class Harness:
    """Fake API: a list of snapshots, one per poll (the last one repeats)."""

    def __init__(self, snapshots, artifacts=()):
        self.snaps = snapshots
        self.artifacts = list(artifacts)
        self.i = 0
        self.clock = T0
        self.downloads = []
        self.lines = []

    def api(self, path):
        snap = self.snaps[min(self.i, len(self.snaps) - 1)]
        if path.endswith("/jobs?per_page=100"):
            return {"jobs": snap.get("jobs", [])}
        if "/artifacts" in path:
            return {"artifacts": [{"name": n} for n in snap.get("artifacts", [])]}
        return {"status": snap.get("run", "in_progress"),
                "conclusion": snap.get("conclusion")}

    def sleep(self, sec):
        self.i += 1
        self.clock += sec

    def run(self, jobs, artifacts=(), deadline=40, stall=10):
        return ci_wait.wait(
            "o/r", "1", jobs, list(artifacts), "/out", deadline, stall,
            api=self.api, download=lambda r, run, n, d: self.downloads.append((n, d)),
            now=lambda: self.clock, sleep=self.sleep, log=self.lines.append)


class CiWaitTests(unittest.TestCase):
    def test_empty_job_list_is_not_done(self):
        h = Harness([{"jobs": []}, {"jobs": []},
                     {"jobs": [job("a")], "conclusion": "success"}])
        self.assertEqual(h.run(["a"]), 0)
        self.assertEqual(h.i, 2)
        self.assertTrue(any("not yet created" in l for l in h.lines))

    def test_missing_job_never_done(self):
        h = Harness([{"jobs": [job("other")]}])
        self.assertEqual(h.run(["a"], deadline=1), 3)

    def test_success_prints_durations(self):
        h = Harness([{"jobs": [job("a", end=95)]}])
        self.assertEqual(h.run(["a"]), 0)
        self.assertTrue(any("job a: success in 1m35s" in l for l in h.lines))

    def test_one_line_per_state_change(self):
        running = {"jobs": [job("a", "in_progress", None, end=None)]}
        h = Harness([running, running, running, {"jobs": [job("a")]}])
        h.run(["a"])
        self.assertEqual(sum("job a: in_progress" in l for l in h.lines), 1)

    def test_failure_reports_step(self):
        steps = [{"name": "Build", "status": "completed", "conclusion": "success"},
                 {"name": "Run tests", "status": "completed", "conclusion": "failure"}]
        h = Harness([{"jobs": [job("a", conclusion="failure", steps=steps)]}])
        self.assertEqual(h.run(["a"]), 1)
        self.assertIn("Run tests", h.lines[-1])

    def test_cancelled_run(self):
        h = Harness([{"run": "completed", "conclusion": "cancelled", "jobs": []}])
        self.assertEqual(h.run(["a"]), 1)
        self.assertIn("cancelled", h.lines[-1])

    def test_stall(self):
        step = {"name": "apt-get", "status": "in_progress",
                "started_at": iso(0)}
        snap = {"jobs": [job("a", "in_progress", None, steps=[step], end=None)]}
        h = Harness([snap])
        self.assertEqual(h.run(["a"], stall=10), 2)
        self.assertIn("apt-get", h.lines[-1])
        self.assertGreater(h.clock - T0, 600)

    def test_deadline(self):
        step = {"name": "s", "status": "in_progress", "started_at": iso(0)}
        snap = {"jobs": [job("a", "in_progress", None, steps=[step], end=None)]}
        h = Harness([snap])
        self.assertEqual(h.run(["a"], deadline=2, stall=99), 3)

    def test_artifact_fetched_before_run_ends(self):
        b = job("b", "in_progress", None, end=None)
        h = Harness([{"jobs": [job("a"), b], "artifacts": ["art"]},
                     {"jobs": [job("a"), job("b")], "artifacts": ["art"]}])
        self.assertEqual(h.run(["a"], ["a:art"]), 0)
        self.assertEqual(h.downloads, [("art", os.path.join("/out", "art"))])
        self.assertEqual(h.i, 0)

    def test_artifact_waits_for_its_job(self):
        run = job("a", "in_progress", None, end=None)
        h = Harness([{"jobs": [run], "artifacts": ["art"]},
                     {"jobs": [job("a")], "artifacts": ["art"]}])
        self.assertEqual(h.run(["a"], ["a:art"]), 0)
        self.assertEqual(h.i, 1)
        self.assertEqual(len(h.downloads), 1)

    def test_missing_artifact_fails(self):
        h = Harness([{"jobs": [job("a")]}])
        self.assertEqual(h.run(["a"], ["art"]), 1)

    def test_api_error(self):
        def bad(path):
            raise RuntimeError("boom")
        lines = []
        rc = ci_wait.wait("o/r", "1", ["a"], [], "/o", 1, 1, api=bad,
                          log=lines.append)
        self.assertEqual(rc, 4)

    def test_gh_api_failure(self):
        r = mock.Mock(returncode=1, stdout="", stderr="nope")
        with mock.patch("subprocess.run", return_value=r):
            with self.assertRaises(RuntimeError):
                ci_wait.gh_api("x")


if __name__ == "__main__":
    unittest.main()
