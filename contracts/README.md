# Kafka message contracts

One example message per topic, version 1 (`event-version: 1` header). These files are the
contract between `generation-service` (Java) and the Python `generation-worker`:

- `services/generation-service/.../GenerationMessageContractTest` serializes/deserializes the Java records against them.
- `services/generation-worker/tests/test_message_contract.py` parses them with the pydantic models.

A field rename on either side breaks one of the two tests. Change a contract by editing the file here
first, then both sides; bump `event-version` for incompatible changes.

| Topic | Producer | Consumer | key |
|---|---|---|---|
| `generation.requested` | generation-service | generation-worker | jobId |
| `generation.progressed` | generation-worker | generation-service | jobId |
| `generation.completed` | generation-worker | generation-service | jobId |
| `generation.failed` | generation-worker | generation-service | jobId |
| `report.save-requested` | generation-service | report-service | jobId |
| `report.created` (compacted) | report-service | dictionary-service, chat-service, generation-service | reportId |
| `job.status-changed` | generation-service | notification-service | jobId |

`report.created` carries two event types under the same key, told apart by the `event-type` header:
`ReportCreated` ([report.created.v1.json](report.created.v1.json)) and `ReportDeleted`
([report.deleted.v1.json](report.deleted.v1.json)). Because compaction keeps the last record per report, a
consumer that replays the topic from the beginning ends with deleted reports deleted. Consumers read the value
as JSON bytes. Producers do not add Spring's `__TypeId__` header (since stage 6). `job.status-changed`:
[job.status-changed.v1.json](job.status-changed.v1.json).

The stage 5 consumers (Java) are not covered by a contract test; they read only the fields they need and ignore
unknown ones.

`report.save-requested` ([report.save-requested.v1.json](report.save-requested.v1.json)) is a command, the save
step of the report generation saga: generation-service sends it when the worker completes, report-service saves
the report (idempotent on `jobId`) and publishes `ReportCreated` with `generationJobId = jobId`, and
generation-service marks the job SUCCEEDED when it sees that event.
