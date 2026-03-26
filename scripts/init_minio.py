"""
MinIO Bucket Initialization Script for RAG Document Storage
初始化 RAG 文档存储 MinIO Bucket

Usage:
    python scripts/init_minio.py [--endpoint ENDPOINT] [--access-key KEY] [--secret-key SECRET]
"""

import argparse
import sys

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    print("Error: minio not installed. Run: pip install minio")
    sys.exit(1)


def create_bucket(
    client: Minio,
    bucket_name: str,
    region: str = "us-east-1",
) -> bool:
    """
    Create a MinIO bucket if it doesn't exist.
    
    Args:
        client: MinIO client
        bucket_name: Name of the bucket
        region: Bucket region
        
    Returns:
        True if bucket was created, False if it already existed
    """
    try:
        if client.bucket_exists(bucket_name):
            print(f"Bucket '{bucket_name}' already exists.")
            return False
        
        client.make_bucket(bucket_name, location=region)
        print(f"Created bucket: {bucket_name}")
        return True
        
    except S3Error as e:
        print(f"Error creating bucket '{bucket_name}': {e}")
        raise


def set_bucket_policy(
    client: Minio,
    bucket_name: str,
    policy_type: str = "private",
) -> None:
    """
    Set bucket access policy.
    
    Args:
        client: MinIO client
        bucket_name: Name of the bucket
        policy_type: "private" or "public-read"
    """
    if policy_type == "private":
        # Delete any existing policy to make it private
        try:
            client.delete_bucket_policy(bucket_name)
            print(f"Set bucket '{bucket_name}' to private access.")
        except S3Error:
            # Policy might not exist, that's fine
            pass
    elif policy_type == "public-read":
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": f"arn:aws:s3:::{bucket_name}",
                },
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": "*"},
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*",
                },
            ],
        }
        import json
        client.set_bucket_policy(bucket_name, json.dumps(policy))
        print(f"Set bucket '{bucket_name}' to public-read access.")


def setup_lifecycle_rules(
    client: Minio,
    bucket_name: str,
) -> None:
    """
    Set up lifecycle rules for automatic cleanup.
    
    Note: MinIO supports lifecycle rules for automatic object expiration.
    This is optional and can be configured based on retention requirements.
    """
    # For now, we don't set any lifecycle rules
    # Documents should be manually deleted or kept indefinitely
    print(f"No lifecycle rules configured for '{bucket_name}' (documents kept indefinitely).")


def main():
    parser = argparse.ArgumentParser(description="Initialize MinIO buckets for RAG")
    parser.add_argument("--endpoint", default="localhost:9000", help="MinIO endpoint")
    parser.add_argument("--access-key", default="minioadmin", help="MinIO access key")
    parser.add_argument("--secret-key", default="minioadmin123", help="MinIO secret key")
    parser.add_argument("--secure", action="store_true", help="Use HTTPS")
    parser.add_argument("--bucket", default="dv-agent-documents", help="Bucket name")
    parser.add_argument("--region", default="us-east-1", help="Bucket region")
    
    args = parser.parse_args()
    
    # Create MinIO client
    print(f"Connecting to MinIO at {args.endpoint}...")
    
    try:
        client = Minio(
            endpoint=args.endpoint,
            access_key=args.access_key,
            secret_key=args.secret_key,
            secure=args.secure,
        )
        
        # Test connection by listing buckets
        buckets = client.list_buckets()
        print(f"Connected successfully! Existing buckets: {[b.name for b in buckets]}")
        
    except Exception as e:
        print(f"Failed to connect to MinIO: {e}")
        sys.exit(1)
    
    # Create buckets
    try:
        print(f"\n--- Creating Document Storage Bucket ---")
        
        # Main document bucket
        create_bucket(client, args.bucket, args.region)
        set_bucket_policy(client, args.bucket, "private")
        setup_lifecycle_rules(client, args.bucket)
        
        # Create folder structure by uploading empty objects
        # (MinIO uses object prefixes as virtual folders)
        folders = [
            "raw/",           # Original uploaded files
            "processed/",     # Processed/extracted content
            "temp/",          # Temporary processing files
        ]
        
        from io import BytesIO
        for folder in folders:
            try:
                # Check if folder marker exists
                client.stat_object(args.bucket, folder)
            except S3Error:
                # Create folder marker
                client.put_object(
                    args.bucket,
                    folder,
                    data=BytesIO(b""),
                    length=0,
                )
                print(f"Created folder: {folder}")
        
        print(f"\n✓ MinIO bucket '{args.bucket}' initialized successfully!")
        
        # Show bucket info
        print(f"\n--- Bucket Information ---")
        print(f"Endpoint: {'https' if args.secure else 'http'}://{args.endpoint}")
        print(f"Bucket: {args.bucket}")
        print(f"Access: Private")
        print(f"Folders: {folders}")
        
    except Exception as e:
        print(f"Error initializing buckets: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
