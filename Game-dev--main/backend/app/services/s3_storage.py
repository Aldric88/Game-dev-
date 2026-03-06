"""S3 file storage service.

Every file created by the frontend is stored in the configured S3 bucket
under:  ``{username}/{project_name}/{filename}``

This keeps each user's generated assets grouped under their own top-level
folder and projects are easy to locate.
"""
from __future__ import annotations

import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3StorageService:
    """Thin wrapper around boto3 S3 operations."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region,
            )
        return self._client

    @property
    def bucket(self) -> str:
        return settings.s3_bucket_name

    def _make_key(self, username: str, project_name: str, filename: str) -> str:
        """Build the S3 object key: ``<username>/<project_name>/<filename>``."""
        username = username.strip().replace(" ", "_")
        project_name = project_name.strip().replace(" ", "_")
        filename = filename.strip()
        return f"{username}/{project_name}/{filename}"

    async def upload_file_content(
        self,
        username: str,
        project_name: str,
        filename: str,
        content: str,
    ) -> dict[str, Any]:
        """Upload a single file (as text content) to S3.

        Returns ``{"key": ..., "url": ...}`` on success.
        """
        key = self._make_key(username, project_name, filename)

        content_type = "text/plain"
        if filename.endswith(".html"):
            content_type = "text/html"
        elif filename.endswith(".css"):
            content_type = "text/css"
        elif filename.endswith(".js"):
            content_type = "application/javascript"
        elif filename.endswith(".json"):
            content_type = "application/json"

        try:
            self._get_client().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )
            url = f"https://{self.bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"
            logger.info("Uploaded %s to s3://%s/%s", filename, self.bucket, key)
            return {"key": key, "url": url}
        except ClientError as e:
            return {"key": key, "url": None, "error": str(e)}

    async def upload_bytes_content(
        self,
        username: str,
        project_name: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Upload a single file (as raw bytes) to S3.

        Used for binary assets such as PNG sprites that cannot be encoded as
        UTF-8 text.  Returns ``{"key": ..., "url": ...}`` on success.
        """
        key = self._make_key(username, project_name, filename)
        try:
            self._get_client().put_object(
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            url = f"https://{self.bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"
            logger.info("Uploaded (binary) %s to s3://%s/%s", filename, self.bucket, key)
            return {"key": key, "url": url}
        except ClientError as e:
            return {"key": key, "url": None, "error": str(e)}

    async def upload_project_files(
        self,
        username: str,
        project_name: str,
        files: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Upload all files for a project and return list of results."""
        results = []
        for filename, content in files.items():
            try:
                result = await self.upload_file_content(username, project_name, filename, content)
                results.append(result)
            except Exception as e:
                logger.warning("Failed to upload %s: %s", filename, e)
                results.append({"key": filename, "url": None, "error": str(e)})
        return results

    async def list_user_files(self, username: str) -> list[dict[str, Any]]:
        """List all objects under a user's folder."""
        prefix = f"{username}/"
        try:
            resp = self._get_client().list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            files = []
            for obj in resp.get("Contents", []):
                files.append({
                    "key": obj.get("Key"),
                    "size": obj.get("Size"),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                })
            return files
        except ClientError as e:
            logger.warning("Failed to list files for %s: %s", username, e)
            return []

    async def list_project_files(self, username: str, project_name: str) -> list[dict[str, Any]]:
        """List all objects under a specific project folder."""
        prefix = f"{username}/{project_name}/"
        try:
            resp = self._get_client().list_objects_v2(Bucket=self.bucket, Prefix=prefix)
            files = []
            for obj in resp.get("Contents", []):
                files.append({
                    "key": obj.get("Key"),
                    "size": obj.get("Size"),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
                })
            return files
        except ClientError as e:
            logger.warning("Failed to list project files for %s/%s: %s", username, project_name, e)
            return []

    async def delete_project_files(self, username: str, project_name: str) -> int:
        """Delete all objects under a project folder. Returns count deleted."""
        files = await self.list_project_files(username, project_name)
        if not files:
            return 0
        objects = [{"Key": f["key"]} for f in files]
        try:
            resp = self._get_client().delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": objects},
            )
            errors = resp.get("Errors", [])
            if errors:
                logger.warning("Failed to delete project files: %s", errors)
            return len(objects) - len(errors)
        except ClientError as e:
            logger.warning("Failed to delete project files: %s", e)
            return 0

    async def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for downloading a private object."""
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


s3_storage = S3StorageService()
