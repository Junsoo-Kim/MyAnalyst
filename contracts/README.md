# Kafka message contracts

One example message per topic, version 1 (`event-version: 1` header). These files are the
contract between the Spring BE (`generation` module) and the Python `generation-worker`:

- `BE/.../GenerationMessageContractTest` serializes/deserializes the Java records against them.
- `services/generation-worker/tests/test_message_contract.py` parses them with the pydantic models.

A field rename on either side breaks one of the two tests. Change a contract by editing the file here
first, then both sides; bump `event-version` for incompatible changes.

| Topic | Producer | Consumer | key |
|---|---|---|---|
| `generation.requested` | BE generation | generation-worker | jobId |
| `generation.progressed` | generation-worker | BE generation | jobId |
| `generation.completed` | generation-worker | BE generation | jobId |
| `generation.failed` | generation-worker | BE generation | jobId |
| `report.created` (compacted) | BE report | dictionary-service, chat-service | reportId |
| `job.status-changed` | BE generation | notification-service | jobId |

`report.created` carries two event types under the same key, told apart by the `event-type` header:
`ReportCreated` ([report.created.v1.json](report.created.v1.json)) and `ReportDeleted`
([report.deleted.v1.json](report.deleted.v1.json)). Because compaction keeps the last record per report, a
consumer that replays the topic from the beginning ends with deleted reports deleted. Consumers read the value
as JSON bytes and ignore Spring's `__TypeId__` header. `job.status-changed`:
[job.status-changed.v1.json](job.status-changed.v1.json).

The stage 5 consumers (Java) are not covered by a contract test; they read only the fields they need and ignore
unknown ones.
