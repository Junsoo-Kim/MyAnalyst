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
