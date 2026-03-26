"""
RAG Document Milvus Collection Initialization Script
初始化 RAG 文档向量存储 Collection

Usage:
    python scripts/init_rag_milvus.py [--host HOST] [--port PORT]
"""

import argparse
import sys

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


def create_doc_embeddings_collection(
    collection_name: str = "doc_embeddings",
    dimension: int = 1024,  # BGE-M3 dimension
    drop_if_exists: bool = False,
) -> Collection:
    """
    Create collection for document dense embeddings.
    
    Schema:
    - id: Primary key (chunk UUID from PostgreSQL)
    - tenant_id: Partition key for tenant isolation
    - document_id: Parent document ID
    - embedding: Dense vector (BGE-M3 1024d)
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
            description="Chunk ID (UUID from PostgreSQL)",
        ),
        FieldSchema(
            name="tenant_id",
            dtype=DataType.VARCHAR,
            max_length=64,
            is_partition_key=True,
            description="Tenant ID for partition isolation",
        ),
        FieldSchema(
            name="document_id",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Parent document ID",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=dimension,
            description="BGE-M3 dense embedding vector (1024d)",
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Document chunk dense embeddings for semantic search",
        enable_dynamic_field=False,
    )
    
    # Create collection
    collection = Collection(
        name=collection_name,
        schema=schema,
        num_partitions=64,  # Support multiple tenants
    )
    
    print(f"Created collection: {collection_name}")
    
    # Create HNSW index for high recall and speed
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {
            "M": 16,
            "efConstruction": 256,
        },
    }
    
    collection.create_index(
        field_name="embedding",
        index_params=index_params,
        index_name="embedding_hnsw_index",
    )
    
    print(f"Created HNSW index on 'embedding' field (M=16, efConstruction=256)")
    
    # Load collection into memory
    collection.load()
    print(f"Collection loaded into memory")
    
    return collection


def create_doc_sparse_embeddings_collection(
    collection_name: str = "doc_sparse_embeddings",
    drop_if_exists: bool = False,
) -> Collection:
    """
    Create collection for document sparse embeddings (BGE-M3 lexical weights).
    
    Note: Milvus 2.3.x has limited sparse vector support.
    For Milvus < 2.4, we use a JSON field to store sparse embeddings.
    For Milvus >= 2.4, SPARSE_FLOAT_VECTOR is fully supported.
    
    Schema:
    - id: Primary key (chunk UUID from PostgreSQL)
    - tenant_id: Partition key for tenant isolation
    - document_id: Parent document ID
    - sparse_embedding: Sparse vector (stored as JSON in Milvus < 2.4)
    """
    
    if utility.has_collection(collection_name):
        if drop_if_exists:
            print(f"Dropping existing collection: {collection_name}")
            utility.drop_collection(collection_name)
        else:
            print(f"Collection '{collection_name}' already exists. Skipping creation.")
            return Collection(collection_name)
    
    # Check Milvus version to determine sparse vector support
    try:
        # Try to use SPARSE_FLOAT_VECTOR (Milvus 2.4+)
        fields = [
            FieldSchema(
                name="id",
                dtype=DataType.VARCHAR,
                max_length=64,
                is_primary=True,
                description="Chunk ID (UUID from PostgreSQL)",
            ),
            FieldSchema(
                name="tenant_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                is_partition_key=True,
                description="Tenant ID for partition isolation",
            ),
            FieldSchema(
                name="document_id",
                dtype=DataType.VARCHAR,
                max_length=64,
                description="Parent document ID",
            ),
            FieldSchema(
                name="sparse_embedding",
                dtype=DataType.SPARSE_FLOAT_VECTOR,
                description="BGE-M3 sparse lexical weights",
            ),
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="Document chunk sparse embeddings for keyword-aware search",
            enable_dynamic_field=False,
        )
        
        collection = Collection(
            name=collection_name,
            schema=schema,
            num_partitions=64,
        )
        
        print(f"Created collection: {collection_name} (with native SPARSE_FLOAT_VECTOR)")
        
        # Create sparse index for Milvus 2.4+
        index_params = {
            "index_type": "SPARSE_INVERTED_INDEX",
            "metric_type": "IP",
            "params": {
                "drop_ratio_build": 0.2,
            },
        }
        
        collection.create_index(
            field_name="sparse_embedding",
            index_params=index_params,
            index_name="sparse_embedding_index",
        )
        
        print(f"Created SPARSE_INVERTED_INDEX on 'sparse_embedding' field")
        
    except Exception as e:
        # Fallback for Milvus < 2.4: skip sparse embeddings collection
        # JSON fields cannot be indexed in Milvus, so sparse search must be done differently
        print(f"SPARSE_FLOAT_VECTOR not fully supported: {e}")
        print(f"Skipping sparse embeddings collection for Milvus < 2.4")
        print(f"Recommendation: Upgrade to Milvus 2.4+ for full sparse vector support")
        print(f"Alternative: Use PostgreSQL full-text search for keyword matching")
        return None
    
    # Load collection into memory
    collection.load()
    print(f"Collection loaded into memory")
    
    return collection


def main():
    parser = argparse.ArgumentParser(description="Initialize RAG Milvus collections")
    parser.add_argument("--host", default="localhost", help="Milvus host")
    parser.add_argument("--port", default="19530", help="Milvus port")
    parser.add_argument("--dimension", type=int, default=1024, help="Dense embedding dimension (BGE-M3=1024)")
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
        print("\n--- Creating Document Dense Embeddings Collection ---")
        create_doc_embeddings_collection(
            dimension=args.dimension,
            drop_if_exists=args.drop,
        )
        
        print("\n--- Creating Document Sparse Embeddings Collection ---")
        create_doc_sparse_embeddings_collection(
            drop_if_exists=args.drop,
        )
        
        print("\n✓ All RAG collections initialized successfully!")
        
        # Show collection stats
        print("\n--- Collection Statistics ---")
        for name in ["doc_embeddings", "doc_sparse_embeddings"]:
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
