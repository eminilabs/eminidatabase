"""S3-compatible object storage client (MinIO in dev — cf. docs/architecture §28:
backups must never live only on the same disk as the primary database).

boto3 is synchronous; every call here runs in a worker thread via asyncio.to_thread
so it doesn't block the agent's event loop (which also needs to keep serving
heartbeats and other requests while a backup uploads).
"""

from __future__ import annotations

import asyncio

import boto3

from app.config import AgentSettings


def _client(settings: AgentSettings):
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _ensure_bucket_sync(settings: AgentSettings) -> None:
    client = _client(settings)
    existing = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if settings.s3_bucket not in existing:
        client.create_bucket(Bucket=settings.s3_bucket)


async def ensure_bucket(settings: AgentSettings) -> None:
    await asyncio.to_thread(_ensure_bucket_sync, settings)


async def upload_bytes(settings: AgentSettings, key: str, data: bytes) -> None:
    def _do():
        _client(settings).put_object(Bucket=settings.s3_bucket, Key=key, Body=data)

    await asyncio.to_thread(_do)


async def download_bytes(settings: AgentSettings, key: str) -> bytes:
    def _do() -> bytes:
        obj = _client(settings).get_object(Bucket=settings.s3_bucket, Key=key)
        return obj["Body"].read()

    return await asyncio.to_thread(_do)


async def delete_object(settings: AgentSettings, key: str) -> None:
    def _do():
        _client(settings).delete_object(Bucket=settings.s3_bucket, Key=key)

    await asyncio.to_thread(_do)
