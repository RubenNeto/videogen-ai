"""
Storage utility — S3 upload (opcional).
Se AWS_S3_BUCKET não estiver configurado, não faz nada.
"""
import logging
from backend.utils.config import settings

logger = logging.getLogger(__name__)


async def upload_to_s3(file_path: str, s3_key: str) -> str | None:
    """Faz upload para S3 se configurado. Retorna URL ou None."""
    if not settings.has_s3:
        return None
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        s3.upload_file(
            file_path, settings.AWS_S3_BUCKET, s3_key,
            ExtraArgs={"ContentType": "video/mp4", "ACL": "public-read"},
        )
        url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"
        logger.info(f"Uploaded to S3: {url}")
        return url
    except Exception as e:
        logger.warning(f"S3 upload failed (non-fatal): {e}")
        return None
