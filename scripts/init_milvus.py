"""
Milvus Collection Initialization Script
DV-Agent Memory System Vector Storage

Usage:
    python scripts/init_milvus.py [--host HOST] [--port PORT]
"""

import argparse
import sys
from typing import Optional

try:
    from pymilvus import (
        connections,
        utility,
        Collection,
        CollectionSchema,
        FieldSchema,
        DataType,
    )
except ImportError:
    print("Error: pymilvus not installed. Run: pip install pymilvus")
    sys.exit(1)


def create_user_memory_collection(
    collection_name: str = "user_memory_vectors",
    dimension: int = 384,
    drop_if_exists: bool = False,
) -> Collection:
    """
    Create collection for user memory vectors.
    
    Schema:
    - id: Primary key (UUID string from PostgreSQL)
    - user_id: Partition key for user isolation
    - embedding: Dense vector for similarity search
    - memory_type: Enum type (fact/preference/event/entity)
    - importance: Float for scoring
    """
    
    if utility.has_collection(collection_name):
        if drop_if_exists:
            print(f"Dropping existing collection: {collection_name}")
            utility.drop_collection(collection_name)
        else:
            print(f"Collection '{collection_name}' already exists. Skipping creation.")
            return Collection(collection_name)
    
    # Define schema
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.VARCHAR,
            max_length=64,
            is_primary=True,
            description="Memory ID (UUID from PostgreSQL)",
        ),
        FieldSchema(
            name="user_id",
            dtype=DataType.VARCHAR,
            max_length=64,
            is_partition_key=True,
            description="User ID for partition isolation",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=dimension,
            description="Memory content embedding vector",
        ),
        FieldSchema(
            name="memory_type",
            dtype=DataType.VARCHAR,
            max_length=16,
            description="Memory type: fact/preference/event/entity",
        ),
        FieldSchema(
            name="importance",
            dtype=DataType.FLOAT,
            description="Memory importance score",
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="User memory vectors for similarity search",
        enable_dynamic_field=False,
    )
    
    # Create collection
    collection = Collection(
        name=collection_name,
        schema=schema,
        num_partitions=64,  # Support up to 64 user partitions per shard
    )
    
    print(f"Created collection: {collection_name}")
    
    # Create index
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 1024},
    }
    
    collection.create_index(
        field_name="embedding",
        index_params=index_params,
        index_name="embedding_index",
    )
    
    print(f"Created IVF_FLAT index on 'embedding' field")
    
    # Load collection into memory
    collection.load()
    print(f"Collection loaded into memory")
    
    return collection


def create_enterprise_knowledge_collection(
    collection_name: str = "enterprise_knowledge",
    dimension: int = 384,
    drop_if_exists: bool = False,
) -> Collection:
    """
    Create collection for enterprise knowledge base.
    
    Schema:
    - id: Primary key (UUID from PostgreSQL)
    - dept_id: Optional department filter
    - embedding: Dense vector
    - category: Knowledge category
    """
    
    if utility.has_collection(collection_name):
        if drop_if_exists:
            print(f"Dropping existing collection: {collection_name}")
            utility.drop_collection(collection_name)
        else:
            print(f"Collection '{collection_name}' already exists. Skipping creation.")
            return Collection(collection_name)
    
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.VARCHAR,
            max_length=64,
            is_primary=True,
            description="Knowledge ID (UUID from PostgreSQL)",
        ),
        FieldSchema(
            name="dept_id",
            dtype=DataType.VARCHAR,
            max_length=64,
            is_partition_key=True,
            description="Department ID (empty string for global)",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=dimension,
            description="Knowledge content embedding vector",
        ),
        FieldSchema(
            name="category",
            dtype=DataType.VARCHAR,
            max_length=128,
            description="Knowledge category",
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Enterprise knowledge base vectors",
        enable_dynamic_field=False,
    )
    
    collection = Collection(
        name=collection_name,
        schema=schema,
        num_partitions=16,
    )
    
    print(f"Created collection: {collection_name}")
    
    # Create index
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 256},
    }
    
    collection.create_index(
        field_name="embedding",
        index_params=index_params,
        index_name="embedding_index",
    )
    
    print(f"Created IVF_FLAT index on 'embedding' field")
    
    collection.load()
    print(f"Collection loaded into memory")
    
    return collection


def main():
    parser = argparse.ArgumentParser(description="Initialize Milvus collections")
    parser.add_argument("--host", default="localhost", help="Milvus host")
    parser.add_argument("--port", default="19530", help="Milvus port")
    parser.add_argument("--dimension", type=int, default=384, help="Embedding dimension")
    parser.add_argument("--drop", action="store_true", help="Drop existing collections")
    
    args = parser.parse_args()
    
    # Connect to Milvus
    print(f"Connecting to Milvus at {args.host}:{args.port}...")
    
    try:
        connections.connect(
            alias="default",
            host=args.host,
            port=args.port,
        )
        print("Connected successfully!")
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")
        sys.exit(1)
    
    # Create collections
    try:
        print("\n--- Creating User Memory Collection ---")
        create_user_memory_collection(
            dimension=args.dimension,
            drop_if_exists=args.drop,
        )
        
        print("\n--- Creating Enterprise Knowledge Collection ---")
        create_enterprise_knowledge_collection(
            dimension=args.dimension,
            drop_if_exists=args.drop,
        )
        
        print("\n✓ All collections initialized successfully!")
        
        # Show collection stats
        print("\n--- Collection Statistics ---")
        for name in ["user_memory_vectors", "enterprise_knowledge"]:
            if utility.has_collection(name):
                col = Collection(name)
                print(f"{name}: {col.num_entities} entities")
        
    except Exception as e:
        print(f"Error creating collections: {e}")
        sys.exit(1)
    finally:
        connections.disconnect("default")


if __name__ == "__main__":
    main()
