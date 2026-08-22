"""Cliente MinIO/S3 para anexos (manifestos, comprovantes)."""
import io
from typing import BinaryIO

from minio import Minio

from app.core.config import settings


def get_client() -> Minio:
    return _client(settings.minio_endpoint, settings.minio_use_ssl)


def get_public_client() -> Minio:
    # Esquema independente: o domínio público pode estar atrás de TLS (Cloudflare/Caddy)
    # mesmo que a conexão interna ao MinIO seja HTTP simples dentro da rede Docker.
    return _client(settings.minio_public_endpoint or settings.minio_endpoint, settings.minio_public_is_secure)


def _client(endpoint: str, secure: bool) -> Minio:
    return Minio(
        endpoint,
        access_key=settings.minio_root_user,
        secret_key=settings.minio_root_password,
        secure=secure,
        region="us-east-1",
    )


def ensure_buckets() -> None:
    client = get_client()
    for bucket in (settings.minio_bucket_manifests, settings.minio_bucket_proofs, settings.minio_bucket_branding):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)


def put_object(bucket: str, key: str, data: bytes, content_type: str) -> None:
    client = get_client()
    client.put_object(bucket, key, io.BytesIO(data), length=len(data), content_type=content_type)


def get_object_bytes(bucket: str, key: str) -> bytes:
    client = get_client()
    response: BinaryIO | None = None
    try:
        response = client.get_object(bucket, key)
        return response.read()
    finally:
        if response is not None:
            response.close()
            response.release_conn()


def get_presigned_url(bucket: str, key: str, expires_seconds: int = 3600) -> str:
    from datetime import timedelta

    client = get_public_client()
    return client.presigned_get_object(bucket, key, expires=timedelta(seconds=expires_seconds))
