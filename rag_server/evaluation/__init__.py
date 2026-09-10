"""Offline RAG evaluation utilities.

The package intentionally has no import-time dependency on Milvus, Torch, or an
LLM. Metric tests and CI can therefore run without a model server.
"""
