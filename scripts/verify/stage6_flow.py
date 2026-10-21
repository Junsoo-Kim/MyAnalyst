"""MSA stage 6 experiments against the compose stack (through api-gateway on :8080).

Like stage5_flow.py, the generation-worker is not started: this script produces generation.* messages itself.

  python scripts/verify/stage6_flow.py migrated USER   # E1: data migrated from the shared DB still works
  python scripts/verify/stage6_flow.py saga            # E2: completed -> SAVING -> report.created -> SUCCEEDED
  python scripts/verify/stage6_flow.py outage          # E3: report-service down while a job completes
  python scripts/verify/stage6_flow.py duplicates      # E4: redelivered completion and save command
  python scripts/verify/stage6_flow.py gateway         # E5: routes without the BE catch-all, market-data cache
  python scripts/verify/stage6_flow.py isolation       # E6: each database holds only its service's tables
"""
import json
import sys
import time

import stage5_flow as f

DATABASES = ("user_db", "report_db", "generation_db", "chat_db", "dictionary_db", "myanalystdb")


def login_existing(user):
    status, _, headers = f.request("POST", "/sessions", body={"userid": user, "password": "password-" + user})
    assert status == 200, status
    return next(v.split(";")[0] for v in headers.get_all("Set-Cookie") if v.startswith("access_token="))


def job(cookie, job_id):
    return f.request("GET", f"/report-jobs/{job_id}", cookie)[1]


def wait_job(cookie, job_id, status, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        body = job(cookie, job_id)
        if body["status"] == status:
            return time.time() - start, body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} never reached {status}: {job(cookie, job_id)}")


def topic_records(topic, key):
    """All records on a topic with the given key: (headers, value)."""
    out = f.docker("exec", f.KAFKA, f"{f.KAFKA_BIN}/kafka-console-consumer.sh", "--bootstrap-server", "localhost:9092",
                   "--topic", topic, "--from-beginning", "--timeout-ms", "6000", "--property", "print.headers=true",
                   "--property", "print.key=true").stdout
    records = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[1] == key:
            records.append((parts[0], parts[2]))
    return records


def report_rows(job_id):
    return f.psql(f"SELECT count(*) FROM reports WHERE generation_job_id='{job_id}'", db="report_db")


def migrated(user):
    cookie = login_existing(user)
    print(f"== E1 data migrated from myanalystdb (user {user}, created on the stage 5 stack)")
    status, reports, _ = f.request("GET", "/reports", cookie)
    print("   GET /reports ->", status, reports)
    rid = reports[0]["reportid"]
    status, detail, _ = f.request("GET", f"/reports/{rid}", cookie)
    print(f"   GET /reports/{rid} ->", status, "content length", len(detail["content"]))
    print(f"   GET /reports/{rid}/dictionary ->", f.request("GET", f"/reports/{rid}/dictionary", cookie)[:2])
    print(f"   GET /reports/{rid}/chat ->", f.request("GET", f"/reports/{rid}/chat", cookie)[:2])
    pending = f.psql("SELECT job_id || ' ' || status FROM report_jobs WHERE status = 'QUEUED'", db="generation_db")
    print("   job left QUEUED before the migration:", pending)
    other = f.login("ivan")
    print(f"   another user: /reports/{rid} ->", f.request("GET", f"/reports/{rid}", other)[0],
          ", dictionary ->", f.request("GET", f"/reports/{rid}/dictionary", other)[0])
    new_id = run_job(f.login("judy"))[1]
    print(f"   new report after the migration gets id {new_id} (ids continue from the copied sequence)")


def run_job(cookie, title="stage6 saga"):
    job_id = f.create_job(cookie, title)
    f.complete([job_id])
    _, body = wait_job(cookie, job_id, "SUCCEEDED")
    return job_id, body["reportId"]


def saga():
    f.ensure_worker_topics()
    cookie = f.login("alice")
    print("== E2 saga: generation.completed -> SAVING + report.save-requested -> report-service -> report.created -> SUCCEEDED")
    job_id = f.create_job(cookie, "stage6 saga")
    sse = f.SseListener(job_id, cookie)
    sse.start()
    time.sleep(1.5)
    f.complete([job_id])
    took, body = wait_job(cookie, job_id, "SUCCEEDED")
    time.sleep(1)
    print("   SSE:", [f"{e['status']}/{e['progress']} {e['message']}" for e in sse.events])
    print(f"   SUCCEEDED, reportId={body['reportId']} ({took:.2f}s after the completion was produced)")
    print("   report_db rows for this job:", report_rows(job_id))
    rid = str(body["reportId"])
    print("   dictionary ->", f.request("GET", f"/reports/{rid}/dictionary", cookie)[0])
    print("== E2b message headers (D11: no __TypeId__)")
    for topic, key in (("report.save-requested", job_id), ("report.created", rid), ("job.status-changed", job_id)):
        records = topic_records(topic, key)
        print(f"   {topic}: {len(records)} record(s), headers of the last: {records[-1][0] if records else '-'}")
    command = json.loads(topic_records("report.save-requested", job_id)[-1][1])
    print("   save command fields:", sorted(command))


def outage():
    f.ensure_worker_topics()
    cookie = f.login("bob")
    print("== E3 report-service stopped while a job completes")
    f.docker("stop", "myanalyst-report-service")
    job_id = f.create_job(cookie, "stage6 outage")
    f.complete([job_id])
    _, body = wait_job(cookie, job_id, "SAVING")
    print("   job ->", body["status"], body["progress"], body["message"])
    print("   GET /reports ->", f.request("GET", "/reports", cookie)[0])
    print("   POST /report-jobs/{id}/cancel while SAVING ->", f.request("POST", f"/report-jobs/{job_id}/cancel", cookie)[:2])
    time.sleep(20)
    print("   after 20s still:", job(cookie, job_id)["status"], "| report rows:", report_rows(job_id))
    f.docker("start", "myanalyst-report-service")
    started = time.time()
    took, body = wait_job(cookie, job_id, "SUCCEEDED", timeout=120)
    print(f"   report-service started -> SUCCEEDED after {took:.1f}s (container start included), "
          f"reportId={body['reportId']}, report rows: {report_rows(job_id)}")


def duplicates():
    f.ensure_worker_topics()
    cookie = f.login("carol")
    print("== E4 redelivery")
    job_id = f.create_job(cookie, "stage6 duplicates")
    f.complete([job_id])
    f.produce("generation.completed", [("GenerationCompleted", job_id, {
        "jobId": job_id, "attempt": 1, "report": f.REPORT_TEXT, "terms": [], "generationTimeSeconds": 1.0})] * 2)
    _, body = wait_job(cookie, job_id, "SUCCEEDED")
    time.sleep(2)
    print("   generation.completed x3 -> save commands:", len(topic_records("report.save-requested", job_id)),
          "| report rows:", report_rows(job_id))
    command = json.loads(topic_records("report.save-requested", job_id)[-1][1])
    f.produce("report.save-requested", [("ReportSaveRequested", job_id, command)] * 2)
    time.sleep(3)
    print("   save command redelivered x2 -> report rows:", report_rows(job_id),
          "| report.created records for the report:", len(topic_records("report.created", str(body["reportId"]))),
          "| job:", job(cookie, job_id)["status"], job(cookie, job_id)["reportId"])


def gateway():
    cookie = f.login("dave")
    print("== E5 gateway routes (no BE catch-all)")
    for method, path in (("GET", "/unknown"), ("GET", "/swagger-ui.html"), ("POST", "/dictionaries"),
                         ("GET", "/reports"), ("GET", "/report-jobs/00000000-0000-0000-0000-000000000000")):
        print(f"   {method} {path} ->", f.request(method, path, cookie, body=[] if method == "POST" else None)[0])
    print("   GET /stocks/삼성전자 without a token ->", f.request("GET", "/stocks/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90")[0])
    for attempt in (1, 2):
        start = time.time()
        status, body, _ = f.request("GET", "/stocks/%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90", cookie)
        print(f"   GET /stocks/삼성전자 #{attempt} -> {status} in {time.time() - start:.2f}s: {str(body)[:90]}")
    keys = f.docker("exec", "myanalyst-redis", "redis-cli", "--scan", "--pattern", "market-data:*").stdout.split()
    print("   redis keys:", keys, "ttl:", [f.docker("exec", "myanalyst-redis", "redis-cli", "ttl", k).stdout.strip() for k in keys])


def isolation():
    print("== E6 tables per database")
    for db in DATABASES:
        tables = f.psql("SELECT string_agg(tablename, ', ' ORDER BY tablename) FROM pg_tables WHERE schemaname='public'", db=db)
        print(f"   {db}: {tables}")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "migrated":
        migrated(sys.argv[2])
    else:
        globals()[mode]()
