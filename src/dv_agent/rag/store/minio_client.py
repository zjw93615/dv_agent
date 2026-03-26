"""
MinIO Object Storage Client
MinIO 对象存储客户端

提供文件的上传、下载和管理功能。
"""

import io
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Optional, Union

logger = logging.getLogger(__name__)


@dataclass
class ObjectInfo:
    """对象信息"""
    
    bucket: str
    key: str
    size: int
    etag: str
    last_modified: Optional[datetime] = None
    content_type: Optional[str] = None
    metadata: dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MinIOClient:
    """
    MinIO 对象存储客户端
    
    封装 MinIO SDK，提供文件存储的 CRUD 操作。
    """
    
    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        secure: bool = False,
        default_bucket: str = "rag-documents",
    ):
        """
        初始化 MinIO 客户端
        
        Args:
            endpoint: MinIO 服务端点
            access_key: 访问密钥
            secret_key: 密钥
            secure: 是否使用 HTTPS
            default_bucket: 默认存储桶
        """
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure
        self.default_bucket = default_bucket
        
        self._client = None
        self._connected = False
    
    def _get_client(self):
        """获取 MinIO 客户端（延迟初始化）"""
        if self._client is None:
            try:
                from minio import Minio
                
                self._client = Minio(
                    self.endpoint,
                    access_key=self.access_key,
                    secret_key=self.secret_key,
                    secure=self.secure,
                )
                self._connected = True
                logger.info(f"Connected to MinIO: {self.endpoint}")
            except ImportError:
                raise ImportError(
                    "minio not installed. Run: pip install minio"
                )
        
        return self._client
    
    def ensure_bucket(self, bucket: Optional[str] = None) -> bool:
        """
        确保存储桶存在
        
        Args:
            bucket: 存储桶名称
            
        Returns:
            是否成功
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                logger.info(f"Created bucket: {bucket}")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure bucket {bucket}: {e}")
            return False
    
    def upload_file(
        self,
        file_path: Union[str, Path],
        object_key: Optional[str] = None,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[ObjectInfo]:
        """
        上传文件
        
        Args:
            file_path: 本地文件路径
            object_key: 对象键（默认使用文件名）
            bucket: 存储桶
            content_type: 内容类型
            metadata: 元数据
            
        Returns:
            对象信息
        """
        file_path = Path(file_path)
        bucket = bucket or self.default_bucket
        object_key = object_key or file_path.name
        
        self.ensure_bucket(bucket)
        client = self._get_client()
        
        try:
            result = client.fput_object(
                bucket,
                object_key,
                str(file_path),
                content_type=content_type,
                metadata=metadata,
            )
            
            return ObjectInfo(
                bucket=bucket,
                key=object_key,
                size=file_path.stat().st_size,
                etag=result.etag,
                content_type=content_type,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            return None
    
    def upload_bytes(
        self,
        data: bytes,
        object_key: str,
        bucket: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[ObjectInfo]:
        """
        上传字节数据
        
        Args:
            data: 字节数据
            object_key: 对象键
            bucket: 存储桶
            content_type: 内容类型
            metadata: 元数据
            
        Returns:
            对象信息
        """
        bucket = bucket or self.default_bucket
        self.ensure_bucket(bucket)
        client = self._get_client()
        
        try:
            data_stream = io.BytesIO(data)
            result = client.put_object(
                bucket,
                object_key,
                data_stream,
                length=len(data),
                content_type=content_type,
                metadata=metadata,
            )
            
            return ObjectInfo(
                bucket=bucket,
                key=object_key,
                size=len(data),
                etag=result.etag,
                content_type=content_type,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Failed to upload bytes to {object_key}: {e}")
            return None
    
    def download_file(
        self,
        object_key: str,
        file_path: Union[str, Path],
        bucket: Optional[str] = None,
    ) -> bool:
        """
        下载文件到本地
        
        Args:
            object_key: 对象键
            file_path: 本地文件路径
            bucket: 存储桶
            
        Returns:
            是否成功
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            client.fget_object(bucket, object_key, str(file_path))
            return True
        except Exception as e:
            logger.error(f"Failed to download {object_key}: {e}")
            return False
    
    def download_bytes(
        self,
        object_key: str,
        bucket: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        下载对象为字节数据
        
        Args:
            object_key: 对象键
            bucket: 存储桶
            
        Returns:
            字节数据
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            response = client.get_object(bucket, object_key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except Exception as e:
            logger.error(f"Failed to download {object_key}: {e}")
            return None
    
    def delete_object(
        self,
        object_key: str,
        bucket: Optional[str] = None,
    ) -> bool:
        """
        删除对象
        
        Args:
            object_key: 对象键
            bucket: 存储桶
            
        Returns:
            是否成功
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            client.remove_object(bucket, object_key)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {object_key}: {e}")
            return False
    
    def get_object_info(
        self,
        object_key: str,
        bucket: Optional[str] = None,
    ) -> Optional[ObjectInfo]:
        """
        获取对象信息
        
        Args:
            object_key: 对象键
            bucket: 存储桶
            
        Returns:
            对象信息
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            stat = client.stat_object(bucket, object_key)
            return ObjectInfo(
                bucket=bucket,
                key=object_key,
                size=stat.size,
                etag=stat.etag,
                last_modified=stat.last_modified,
                content_type=stat.content_type,
                metadata=dict(stat.metadata) if stat.metadata else {},
            )
        except Exception as e:
            logger.error(f"Failed to get info for {object_key}: {e}")
            return None
    
    def object_exists(
        self,
        object_key: str,
        bucket: Optional[str] = None,
    ) -> bool:
        """
        检查对象是否存在
        
        Args:
            object_key: 对象键
            bucket: 存储桶
            
        Returns:
            是否存在
        """
        return self.get_object_info(object_key, bucket) is not None
    
    def list_objects(
        self,
        prefix: str = "",
        bucket: Optional[str] = None,
        recursive: bool = True,
    ) -> list[ObjectInfo]:
        """
        列出对象
        
        Args:
            prefix: 前缀过滤
            bucket: 存储桶
            recursive: 是否递归
            
        Returns:
            对象信息列表
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            objects = client.list_objects(
                bucket,
                prefix=prefix,
                recursive=recursive,
            )
            
            return [
                ObjectInfo(
                    bucket=bucket,
                    key=obj.object_name,
                    size=obj.size or 0,
                    etag=obj.etag or "",
                    last_modified=obj.last_modified,
                )
                for obj in objects
            ]
        except Exception as e:
            logger.error(f"Failed to list objects: {e}")
            return []
    
    def get_presigned_url(
        self,
        object_key: str,
        bucket: Optional[str] = None,
        expires: int = 3600,
    ) -> Optional[str]:
        """
        获取预签名 URL
        
        Args:
            object_key: 对象键
            bucket: 存储桶
            expires: 过期时间（秒）
            
        Returns:
            预签名 URL
        """
        bucket = bucket or self.default_bucket
        client = self._get_client()
        
        try:
            url = client.presigned_get_object(
                bucket,
                object_key,
                expires=timedelta(seconds=expires),
            )
            return url
        except Exception as e:
            logger.error(f"Failed to get presigned URL for {object_key}: {e}")
            return None
    
    def copy_object(
        self,
        source_key: str,
        dest_key: str,
        source_bucket: Optional[str] = None,
        dest_bucket: Optional[str] = None,
    ) -> bool:
        """
        复制对象
        
        Args:
            source_key: 源对象键
            dest_key: 目标对象键
            source_bucket: 源存储桶
            dest_bucket: 目标存储桶
            
        Returns:
            是否成功
        """
        from minio.commonconfig import CopySource
        
        source_bucket = source_bucket or self.default_bucket
        dest_bucket = dest_bucket or self.default_bucket
        client = self._get_client()
        
        try:
            client.copy_object(
                dest_bucket,
                dest_key,
                CopySource(source_bucket, source_key),
            )
            return True
        except Exception as e:
            logger.error(f"Failed to copy {source_key} to {dest_key}: {e}")
            return False
    
    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connected
    
    @classmethod
    def from_config(cls, config: dict) -> "MinIOClient":
        """
        从配置创建客户端
        
        Args:
            config: 配置字典
            
        Returns:
            MinIOClient 实例
        """
        return cls(
            endpoint=config.get("endpoint", "localhost:9000"),
            access_key=config.get("access_key", "minioadmin"),
            secret_key=config.get("secret_key", "minioadmin"),
            secure=config.get("secure", False),
            default_bucket=config.get("default_bucket", "rag-documents"),
        )
