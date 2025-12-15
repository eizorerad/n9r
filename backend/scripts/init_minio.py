"""Initialize MinIO buckets for n9r."""

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

# Bucket names
MAIN_BUCKET = settings.minio_bucket
REPO_CONTENT_BUCKET = "repo-content"


def init_minio():
    """Create the required bucket structure in MinIO."""
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    # Create main bucket if it doesn't exist
    bucket_name = MAIN_BUCKET
    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' created successfully.")
    else:
        print(f"Bucket '{bucket_name}' already exists.")

    # Create repo-content bucket for repository file caching
    if not client.bucket_exists(REPO_CONTENT_BUCKET):
        client.make_bucket(REPO_CONTENT_BUCKET)
        print(f"Bucket '{REPO_CONTENT_BUCKET}' created successfully.")
    else:
        print(f"Bucket '{REPO_CONTENT_BUCKET}' already exists.")

    # Create folder structure by uploading empty placeholder files
    # MinIO doesn't have real folders, but we can create the structure
    folders = [
        "reports/.gitkeep",
        "logs/.gitkeep",
        "artifacts/.gitkeep",
    ]

    from io import BytesIO

    for folder in folders:
        try:
            # Check if the object exists
            client.stat_object(bucket_name, folder)
            print(f"Folder marker '{folder}' already exists.")
        except S3Error as e:
            if e.code == "NoSuchKey":
                # Create empty placeholder
                client.put_object(
                    bucket_name,
                    folder,
                    BytesIO(b""),
                    0,
                )
                print(f"Folder marker '{folder}' created.")
            else:
                raise

    print("\nMinIO initialization complete.")
    print("Bucket structure:")
    print(f"  {bucket_name}/")
    print("    ├── reports/      # Analysis reports (JSON, HTML)")
    print("    ├── logs/         # Agent and analysis logs")
    print("    └── artifacts/    # Code artifacts and diffs")
    print(f"  {REPO_CONTENT_BUCKET}/")
    print("    └── <repo_id>/<commit_sha>/<object_id>  # Cached repository files")


if __name__ == "__main__":
    init_minio()
