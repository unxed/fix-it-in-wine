#!/usr/bin/env python3
"""Wait for named jobs of a GitHub Actions run and fetch their artifacts early.

  ci_wait.py --repo OWNER/REPO --run RUN_ID --job NAME [--job NAME]...
             [--artifact [JOB:]NAME]... [--out DIR]
             [--deadline-min N] [--stall-min M]

A job counts as done only if it exists and is completed (an empty or missing
job list is "not yet"). One line is printed per state change. Artifacts are
downloaded as soon as they exist (with JOB:NAME, once that job has completed),
before the rest of the run ends. Needs the `gh` CLI.

Exit codes: 0 all named jobs succeeded; 1 job or run failed; 2 stalled;
3 deadline exceeded; 4 usage or gh error.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time

POLL_SEC = 20
BAD = ("failure", "cancelled", "timed_out", "startup_failure", "action_required")


def gh_api(path):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gh api %s failed: %s" % (path, r.stderr.strip()))
    return json.loads(r.stdout)


def gh_download(repo, run, name, dest):
    r = subprocess.run(
        ["gh", "run", "download", str(run), "-R", repo, "-n", name, "-D", dest],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("download of %s failed: %s" % (name, r.stderr.strip()))


def parse_time(s):
    if not s:
        return None
    return datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc)


def fmt_dur(sec):
    sec = int(sec)
    return "%dm%02ds" % (sec // 60, sec % 60)


def job_duration(job):
    a, b = parse_time(job.get("started_at")), parse_time(job.get("completed_at"))
    return (b - a).total_seconds() if a and b else None


def failed_steps(job):
    return [s["name"] for s in job.get("steps") or []
            if s.get("conclusion") in BAD]


def current_step(job):
    for s in job.get("steps") or []:
        if s.get("status") == "in_progress":
            return s
    return None


def split_artifact(spec):
    if ":" in spec:
        job, name = spec.split(":", 1)
        return job, name
    return None, spec


def wait(repo, run, jobs, artifacts, out, deadline_min, stall_min,
         api=gh_api, download=gh_download, now=time.time, sleep=time.sleep,
         log=print):
    """Returns the exit code."""
    start = now()
    last = {}
    fetched = set()
    arts = [split_artifact(a) for a in artifacts]
    while True:
        try:
            run_info = api("repos/%s/actions/runs/%s" % (repo, run))
            jobs_info = api("repos/%s/actions/runs/%s/jobs?per_page=100"
                            % (repo, run)).get("jobs", [])
            art_names = set()
            if arts:
                lst = api("repos/%s/actions/runs/%s/artifacts?per_page=100"
                          % (repo, run)).get("artifacts", [])
                art_names = {a["name"] for a in lst if not a.get("expired")}
        except RuntimeError as e:
            log("ci_wait: %s" % e)
            return 4
        by_name = {j["name"]: j for j in jobs_info}
        t = now()

        def say(key, msg):
            if last.get(key) != msg:
                last[key] = msg
                log("[%s] %s" % (fmt_dur(t - start), msg))

        say("run", "run: %s%s" % (run_info.get("status"),
            "/" + run_info["conclusion"] if run_info.get("conclusion") else ""))
        if run_info.get("conclusion") == "cancelled":
            log("ci_wait: FAIL run %s was cancelled (a newer push to the "
                "branch may have cancelled it)" % run)
            return 1
        for name in jobs:
            j = by_name.get(name)
            if j is None:
                say(name, "job %s: not yet created" % name)
                continue
            st = j.get("status")
            if st == "completed":
                say(name, "job %s: completed/%s" % (name, j.get("conclusion")))
            else:
                step = current_step(j)
                say(name, "job %s: %s%s" % (name, st,
                    ", step '%s'" % step["name"] if step else ""))
        # Artifacts first, so they are read even if the job later fails.
        for jname, aname in arts:
            if aname in fetched or aname not in art_names:
                continue
            if jname and (by_name.get(jname) or {}).get("status") != "completed":
                continue
            dest = os.path.join(out, aname)
            try:
                download(repo, run, aname, dest)
            except RuntimeError as e:
                log("ci_wait: %s" % e)
                continue
            fetched.add(aname)
            log("[%s] artifact %s downloaded to %s" % (fmt_dur(t - start), aname, dest))
        for name in jobs:
            j = by_name.get(name)
            if j and j.get("status") == "completed" and j.get("conclusion") in BAD:
                steps = failed_steps(j)
                log("ci_wait: FAIL job %s %s%s" % (name, j["conclusion"],
                    "; failed step(s): " + ", ".join(steps) if steps else ""))
                return 1
        for name in jobs:
            j = by_name.get(name)
            if not j or j.get("status") != "in_progress":
                continue
            step = current_step(j)
            began = parse_time(step.get("started_at")) if step else None
            if began:
                age = datetime.datetime.fromtimestamp(
                    t, datetime.timezone.utc) - began
                if age.total_seconds() > stall_min * 60:
                    log("ci_wait: STALL job %s step '%s' running %s (limit %d min); "
                        "investigate, do not keep waiting" % (
                            name, step["name"], fmt_dur(age.total_seconds()), stall_min))
                    return 2
        done = all((by_name.get(n) or {}).get("status") == "completed" for n in jobs)
        if done and jobs:
            for name in jobs:
                d = job_duration(by_name[name])
                log("job %s: %s in %s" % (name, by_name[name].get("conclusion"),
                    fmt_dur(d) if d is not None else "?"))
            missing = [a for _, a in arts if a not in fetched]
            if missing:
                log("ci_wait: FAIL artifact(s) not available: " + ", ".join(missing))
                return 1
            return 0
        if t - start > deadline_min * 60:
            log("ci_wait: DEADLINE exceeded (%d min)" % deadline_min)
            return 3
        sleep(POLL_SEC)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--repo", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--job", action="append", required=True)
    p.add_argument("--artifact", action="append", default=[],
                   help="NAME or JOB:NAME")
    p.add_argument("--out", default="ci-artifacts")
    p.add_argument("--deadline-min", type=int, default=40)
    p.add_argument("--stall-min", type=int, default=10)
    a = p.parse_args(argv)
    return wait(a.repo, a.run, a.job, a.artifact, a.out,
                a.deadline_min, a.stall_min)


if __name__ == "__main__":
    sys.exit(main())
