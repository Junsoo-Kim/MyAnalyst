"""MSA stage 5 experiments against the compose stack (through api-gateway on :8080).

The generation-worker is not started: this script plays its part by producing generation.progressed /
generation.completed messages (contracts/) with kafka-console-producer inside the broker container, so a report
is saved by BE and published on report.created exactly as in the real flow, without the RAG stack.

  python scripts/verify/stage5_flow.py flow             # E1-E4: ownership, chat, SSE filtering, delete
  python scripts/verify/stage5_flow.py bulk N DELETE    # create N reports, delete DELETE of them
  python scripts/verify/stage5_flow.py replay           # E5: rebuild chat-service copies from report.created
"""
import http.client
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

GATEWAY = "http://localhost:8080"
KAFKA = "myanalyst-kafka"
KAFKA_BIN = "/opt/kafka/bin"
POSTGRES = "myanalyst-postgres"


def request(method, path, cookie=None, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GATEWAY + path, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw and raw[0] in "[{" else raw), resp.headers
    except urllib.error.HTTPError as err:
        raw = err.read().decode()
        return err.code, raw, err.headers


def login(name):
    user = f"{name}-{uuid.uuid4().hex[:6]}"
    request("POST", "/users", body={"userid": user, "password": "password-" + user})
    status, _, headers = request("POST", "/sessions", body={"userid": user, "password": "password-" + user})
    assert status == 200, status
    for value in headers.get_all("Set-Cookie"):
        if value.startswith("access_token="):
            return value.split(";")[0]
    raise AssertionError("no access_token cookie")


def docker(*args, stdin=None):
    return subprocess.run(["docker", *args], input=stdin, capture_output=True, text=True, encoding="utf-8")


def ensure_worker_topics():
    for topic in ("generation.progressed", "generation.completed", "generation.failed"):
        docker("exec", KAFKA, f"{KAFKA_BIN}/kafka-topics.sh", "--bootstrap-server", "localhost:9092",
               "--create", "--if-not-exists", "--topic", topic, "--partitions", "3")


def produce(topic, messages):
    """messages: list of (event_type, key, payload). Headers mirror the Python worker."""
    lines = [f"event-type:{t},event-version:1\t{k}\t{json.dumps(p, ensure_ascii=False)}" for t, k, p in messages]
    result = docker("exec", "-i", KAFKA, f"{KAFKA_BIN}/kafka-console-producer.sh", "--bootstrap-server",
                    "localhost:9092", "--topic", topic, "--property", "parse.headers=true",
                    "--property", "parse.key=true", stdin="\n".join(lines) + "\n")
    assert result.returncode == 0, result.stderr


def psql(sql):
    return docker("exec", POSTGRES, "psql", "-U", "postgres", "-d", "myanalystdb", "-tA", "-c", sql).stdout.strip()


def create_job(cookie, title):
    status, body, _ = request("POST", "/report-jobs", cookie, {
        "title": title, "chapter": "1. Summary", "indicator": "PER", "company": "Samsung", "date": "2026-10-21"}, {"Idempotency-Key": str(uuid.uuid4())})
    assert status == 202, (status, body)
    return body["jobId"]


REPORT_TEXT = ("### 1. Summary\n\nStage 5 verification report. Samsung trades at a PER of 12x and an EV/EBITDA "
               "of 5x; memory prices recovered in the last two quarters and operating margin improved. ") * 3


def complete(job_ids, report_text=REPORT_TEXT):
    produce("generation.progressed", [("GenerationProgressed", j, {
        "jobId": j, "attempt": 1, "stage": "STARTED", "progress": 0, "message": "Started"}) for j in job_ids])
    time.sleep(1)
    produce("generation.progressed", [("GenerationProgressed", j, {
        "jobId": j, "attempt": 1, "stage": "SECTION_1", "progress": 50, "message": "Generating section 1"})
        for j in job_ids])
    produce("generation.completed", [("GenerationCompleted", j, {
        "jobId": j, "attempt": 1, "report": report_text,
        "terms": [{"term": "PER", "explanation": "Price to earnings ratio"},
                  {"term": "EV/EBITDA", "explanation": "Enterprise value multiple"}],
        "generationTimeSeconds": 1.0}) for j in job_ids])


def wait_report_id(cookie, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, body, _ = request("GET", f"/report-jobs/{job_id}", cookie)
        if status == 200 and body["status"] == "SUCCEEDED":
            return body["reportId"]
        time.sleep(0.3)
    raise AssertionError(f"job {job_id} did not succeed")


def wait_status(path, cookie, expected, timeout=30):
    """Return seconds until GET path answers with the expected status."""
    start = time.time()
    while time.time() - start < timeout:
        status, _, _ = request("GET", path, cookie)
        if status == expected:
            return time.time() - start
        time.sleep(0.05)
    raise AssertionError(f"{path} never returned {expected}")


class SseListener(threading.Thread):
    def __init__(self, job_id, cookie):
        super().__init__(daemon=True)
        self.job_id, self.cookie, self.events, self.status = job_id, cookie, [], None

    def run(self):
        conn = http.client.HTTPConnection("localhost", 8080, timeout=60)
        conn.request("GET", f"/report-jobs/{self.job_id}/events",
                     headers={"Cookie": self.cookie, "Accept": "text/event-stream"})
        resp = conn.getresponse()
        self.status = resp.status
        if resp.status != 200:
            return
        try:
            while True:
                line = resp.readline().decode()
                if not line:
                    return
                if line.startswith("data:"):
                    self.events.append(json.loads(line[5:]))
        except (TimeoutError, OSError):
            return


def flow():
    ensure_worker_topics()
    alice, bob = login("alice"), login("bob")

    print("== E1 report -> report.created -> dictionary/chat copies")
    job_id = create_job(alice, "Stage5 report")
    alice_sse, bob_sse = SseListener(job_id, alice), SseListener(job_id, bob)
    alice_sse.start(); bob_sse.start()
    time.sleep(1.5)
    complete([job_id])
    report_id = wait_report_id(alice, job_id)
    saved_at = time.time()
    print(f"   job {job_id} SUCCEEDED, reportId={report_id}")
    t_dict = wait_status(f"/reports/{report_id}/dictionary", alice, 200)
    print(f"   GET /reports/{report_id}/dictionary (alice) 200 after {time.time() - saved_at:.2f}s "
          f"(polled {t_dict:.2f}s): {request('GET', f'/reports/{report_id}/dictionary', alice)[1]}")
    print("   copies:", psql(f"SELECT 'dictionary_reports', user_id FROM dictionary_reports WHERE report_id={report_id} "
                             f"UNION ALL SELECT 'chat_reports', user_id || ' content=' || length(content) "
                             f"FROM chat_reports WHERE report_id={report_id}").replace("\n", " | "))

    print("== E2 ownership from the event copy (no call to BE)")
    print("   dictionary bob ->", request("GET", f"/reports/{report_id}/dictionary", bob)[0])
    print("   dictionary unknown report ->", request("GET", "/reports/999999/dictionary", alice)[0])
    status, body, _ = request("POST", "/chat", alice, {"reportid": report_id, "question": "PER이 뭐야?"})
    print("   POST /chat alice ->", status, str(body)[:80])
    print("   POST /chat bob ->", request("POST", "/chat", bob, {"reportid": report_id, "question": "hi"})[0])
    print("   GET /reports/{id}/chat alice ->", request("GET", f"/reports/{report_id}/chat", alice)[:2])
    print("   GET /reports/{id}/chat bob ->", request("GET", f"/reports/{report_id}/chat", bob)[0])

    print("== E3 SSE through notification-service, filtered by job owner")
    time.sleep(1)
    print(f"   alice: HTTP {alice_sse.status}, events:",
          [f"{e['status']}/{e['progress']}" for e in alice_sse.events])
    print(f"   bob (same jobId): HTTP {bob_sse.status}, events: {len(bob_sse.events)}")
    late = SseListener(job_id, alice); late.start(); time.sleep(1.5)
    print("   alice subscribing after completion gets the last snapshot:",
          [f"{e['status']}" for e in late.events])

    print("== E4 delete -> ReportDeleted on report.created (same key) -> copies and chat history removed")
    print("   DELETE /reports/{id} ->", request("DELETE", f"/reports/{report_id}", alice)[0])
    t_gone = wait_status(f"/reports/{report_id}/dictionary", alice, 404)
    t_chat = wait_status(f"/reports/{report_id}/chat", alice, 404)
    print(f"   dictionary 404 after {t_gone:.2f}s, chat 404 after {t_chat:.2f}s")
    print("   rows left:", psql(
        f"SELECT (SELECT count(*) FROM dictionary WHERE reportid={report_id}), "
        f"(SELECT count(*) FROM dictionary_reports WHERE report_id={report_id}), "
        f"(SELECT count(*) FROM chats WHERE reportid={report_id}), "
        f"(SELECT count(*) FROM chat_reports WHERE report_id={report_id})"))


def bulk(count, deletes):
    ensure_worker_topics()
    cookie = login("carol")
    jobs = [create_job(cookie, f"bulk {i}") for i in range(count)]
    complete(jobs)
    report_ids = [wait_report_id(cookie, j) for j in jobs]
    for report_id in report_ids[:deletes]:
        assert request("DELETE", f"/reports/{report_id}", cookie)[0] == 200
    print(f"created {count} reports ({min(report_ids)}..{max(report_ids)}), deleted {deletes}: {report_ids[:deletes]}")


def group_lag(group):
    """Per-partition (current, end) offsets of a consumer group on report.created."""
    out = docker("exec", KAFKA, f"{KAFKA_BIN}/kafka-consumer-groups.sh", "--bootstrap-server", "localhost:9092",
                 "--describe", "--group", group).stdout
    rows = [line.split() for line in out.splitlines() if line.startswith(group + " ") and "report.created" in line]
    return [(int(r[3]) if r[3].isdigit() else -1, int(r[4])) for r in rows]


def replay():
    count_sql = ("SELECT (SELECT count(*) FROM reports), (SELECT count(*) FROM reports WHERE generation_job_id "
                 "IS NOT NULL), (SELECT count(*) FROM chat_reports), (SELECT count(*) FROM chat_reports c WHERE NOT "
                 "EXISTS (SELECT 1 FROM reports r WHERE r.reportid = c.report_id)), (SELECT count(*) FROM chats)")
    header = "reports|published reports|chat_reports|copies of deleted reports|chats"
    print(f"before         {header}:", psql(count_sql))
    docker("stop", "myanalyst-chat-service")
    psql("TRUNCATE chat_reports")
    print(f"after truncate {header}:", psql(count_sql))
    reset = docker("exec", KAFKA, f"{KAFKA_BIN}/kafka-consumer-groups.sh", "--bootstrap-server", "localhost:9092",
                   "--group", "chat", "--topic", "report.created", "--reset-offsets", "--to-earliest", "--execute")
    print("offsets reset to earliest:", sorted(group_lag("chat")), "(current, end) per partition" if reset.returncode == 0
          else reset.stderr)
    messages = sum(end for _, end in group_lag("chat"))
    start = time.time()
    docker("start", "myanalyst-chat-service")
    caught_up = None
    while time.time() - start < 180:
        lag = group_lag("chat")
        if lag and all(current == end for current, end in lag):
            caught_up = time.time() - start
            break
        time.sleep(0.2)
    log = docker("logs", "myanalyst-chat-service").stdout + docker("logs", "myanalyst-chat-service").stderr
    started = [line for line in log.splitlines() if "Started ChatServiceApplication" in line]
    print(f"replayed {messages} messages (ReportCreated + ReportDeleted); consumer caught up {caught_up:.1f}s "
          f"after container start; JVM start line: {started[-1].split('Started ')[-1] if started else '?'}")
    print(f"after replay   {header}:", psql(count_sql))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "flow"
    if mode == "flow":
        flow()
    elif mode == "bulk":
        bulk(int(sys.argv[2]), int(sys.argv[3]))
    elif mode == "replay":
        replay()
