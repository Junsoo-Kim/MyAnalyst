# ingest.py — knowledge-ingest: 검색 저장소에 쓰는 배치 작업. API와 같은 이미지에서 다른 명령으로 실행한다.
#
#   python ingest.py bm25 [--force]        Milvus 텍스트를 OpenSearch BM25 인덱스에 색인
#   python ingest.py rebuild-milvus ...    tools/rebuild_milvus_collections.py 실행
import argparse
import json
import sys
from datetime import datetime, timezone

import config
import embedding
import hybrid_search


def publish_indexed(index: str, documents: int) -> None:
    """색인이 끝났음을 knowledge.indexed로 알린다. Kafka 설정이 없으면 건너뛴다(로컬 단독 실행)."""
    if not config.KAFKA_BOOTSTRAP_SERVERS:
        return
    from confluent_kafka import KafkaError, KafkaException, Producer
    from confluent_kafka.admin import AdminClient, NewTopic

    # 발행하는 쪽이 토픽을 소유한다. 브로커 자동 생성은 꺼져 있으므로 없으면 만든다.
    admin = AdminClient({"bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS})
    for future in admin.create_topics([NewTopic(config.KNOWLEDGE_INDEXED_TOPIC, num_partitions=1,
                                                replication_factor=config.KAFKA_TOPIC_REPLICAS)]).values():
        try:
            future.result()
        except KafkaException as e:
            if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise

    producer = Producer({"bootstrap.servers": config.KAFKA_BOOTSTRAP_SERVERS, "acks": "all"})
    payload = {"index": index, "documents": documents, "indexedAt": datetime.now(timezone.utc).isoformat()}
    producer.produce(
        config.KNOWLEDGE_INDEXED_TOPIC,
        key=index,
        value=json.dumps(payload).encode("utf-8"),
        headers=[("event-type", b"KnowledgeIndexed"), ("event-version", b"1")],
    )
    remaining = producer.flush(10)
    if remaining:
        raise RuntimeError(f"knowledge.indexed not delivered ({remaining} pending)")
    print(f"[ingest] knowledge.indexed published: {payload}")


def run_bm25(force: bool) -> None:
    embedding.initialize_models()  # 질의와 같은 WordPiece 토크나이저로 색인해야 한다
    count = hybrid_search.build_bm25_index(force=force)
    print(f"[ingest] BM25 index '{config.OPENSEARCH_INDEX}' documents={count}")
    publish_indexed(config.OPENSEARCH_INDEX, count)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="MyAnalyst knowledge ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    bm25 = sub.add_parser("bm25", help="Milvus 컬렉션 텍스트를 OpenSearch에 색인")
    bm25.add_argument("--force", action="store_true", help="기존 문서를 지우고 다시 색인")
    sub.add_parser("rebuild-milvus", help="Milvus 컬렉션 재구축 도구 실행")

    args, rest = parser.parse_known_args(argv)
    if args.command == "bm25":
        run_bm25(args.force)
        return 0
    if args.command == "rebuild-milvus":
        import runpy

        sys.argv = ["rebuild_milvus_collections.py", *rest]
        runpy.run_path("tools/rebuild_milvus_collections.py", run_name="__main__")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
