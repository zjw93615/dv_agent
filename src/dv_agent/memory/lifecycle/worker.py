"""
Memory Lifecycle Worker
记忆生命周期后台任务

提供定时任务调度，自动执行：
- 重要性权重更新
- 软遗忘扫描
- 归档执行
- PG-Milvus 一致性检查
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from uuid import UUID

from .updater import ImportanceUpdater
from .forgetter import MemoryForgetter, ForgetResult
from ..long_term.pg_store import PostgresMemoryStore
from ..long_term.milvus_store import MilvusMemoryStore

logger = logging.getLogger(__name__)


@dataclass
class TaskConfig:
    """任务配置"""
    enabled: bool = True
    interval_seconds: int = 3600  # 默认1小时
    last_run: Optional[datetime] = None
    run_count: int = 0
    error_count: int = 0


@dataclass
class WorkerConfig:
    """Worker 配置"""
    # 重要性更新任务
    importance_update: TaskConfig = field(
        default_factory=lambda: TaskConfig(interval_seconds=3600)
    )
    
    # 软遗忘扫描任务
    soft_forget_scan: TaskConfig = field(
        default_factory=lambda: TaskConfig(interval_seconds=86400)  # 每天
    )
    
    # 归档执行任务
    archive_execution: TaskConfig = field(
        default_factory=lambda: TaskConfig(interval_seconds=86400)  # 每天
    )
    
    # 硬删除任务
    hard_delete: TaskConfig = field(
        default_factory=lambda: TaskConfig(interval_seconds=604800)  # 每周
    )
    
    # PG-Milvus 一致性检查
    consistency_check: TaskConfig = field(
        default_factory=lambda: TaskConfig(interval_seconds=21600)  # 每6小时
    )


@dataclass
class TaskResult:
    """任务执行结果"""
    task_name: str
    success: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class MemoryLifecycleWorker:
    """
    记忆生命周期后台 Worker
    
    管理所有与记忆生命周期相关的定时任务。
    可以作为独立后台协程运行，也可以手动触发单个任务。
    """
    
    def __init__(
        self,
        pg_store: PostgresMemoryStore,
        milvus_store: Optional[MilvusMemoryStore] = None,
        updater: Optional[ImportanceUpdater] = None,
        forgetter: Optional[MemoryForgetter] = None,
        config: Optional[WorkerConfig] = None,
    ):
        """
        初始化 Worker
        
        Args:
            pg_store: PostgreSQL 存储
            milvus_store: Milvus 存储
            updater: 重要性更新器
            forgetter: 遗忘器
            config: Worker 配置
        """
        self.pg = pg_store
        self.milvus = milvus_store
        self.updater = updater or ImportanceUpdater(pg_store)
        self.forgetter = forgetter or MemoryForgetter(pg_store, milvus_store)
        self.config = config or WorkerConfig()
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """启动后台 Worker"""
        if self._running:
            logger.warning("Worker is already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("MemoryLifecycleWorker started")
    
    async def stop(self) -> None:
        """停止后台 Worker"""
        self._running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("MemoryLifecycleWorker stopped")
    
    async def _run_loop(self) -> None:
        """主循环"""
        while self._running:
            try:
                # 检查并执行各项任务
                await self._check_and_run_tasks()
                
                # 等待一段时间再检查
                await asyncio.sleep(60)  # 每分钟检查一次
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}", exc_info=True)
                await asyncio.sleep(300)  # 出错后等待5分钟
    
    async def _check_and_run_tasks(self) -> None:
        """检查并运行到期的任务"""
        now = datetime.utcnow()
        
        # 重要性更新
        if self._should_run(self.config.importance_update, now):
            await self._run_task(
                "importance_update",
                self._task_importance_update,
                self.config.importance_update,
            )
        
        # 软遗忘扫描
        if self._should_run(self.config.soft_forget_scan, now):
            await self._run_task(
                "soft_forget_scan",
                self._task_soft_forget,
                self.config.soft_forget_scan,
            )
        
        # 归档执行
        if self._should_run(self.config.archive_execution, now):
            await self._run_task(
                "archive_execution",
                self._task_archive,
                self.config.archive_execution,
            )
        
        # 硬删除
        if self._should_run(self.config.hard_delete, now):
            await self._run_task(
                "hard_delete",
                self._task_hard_delete,
                self.config.hard_delete,
            )
        
        # 一致性检查
        if self._should_run(self.config.consistency_check, now):
            await self._run_task(
                "consistency_check",
                self._task_consistency_check,
                self.config.consistency_check,
            )
    
    def _should_run(self, task_config: TaskConfig, now: datetime) -> bool:
        """判断任务是否应该运行"""
        if not task_config.enabled:
            return False
        
        if task_config.last_run is None:
            return True
        
        elapsed = (now - task_config.last_run).total_seconds()
        return elapsed >= task_config.interval_seconds
    
    async def _run_task(
        self,
        name: str,
        func: Callable,
        task_config: TaskConfig,
    ) -> TaskResult:
        """执行任务并记录结果"""
        start_time = datetime.utcnow()
        result = TaskResult(task_name=name, success=False, duration_ms=0)
        
        try:
            details = await func()
            result.success = True
            result.details = details or {}
            task_config.run_count += 1
            
        except Exception as e:
            result.error = str(e)
            task_config.error_count += 1
            logger.error(f"Task {name} failed: {e}", exc_info=True)
        
        task_config.last_run = datetime.utcnow()
        result.duration_ms = (task_config.last_run - start_time).total_seconds() * 1000
        
        logger.info(
            f"Task {name} completed: success={result.success}, "
            f"duration={result.duration_ms:.1f}ms"
        )
        
        return result
    
    # ========== 具体任务实现 ==========
    
    async def _task_importance_update(self) -> dict[str, Any]:
        """重要性更新任务"""
        stats = await self.updater.batch_update(limit=1000)
        return stats
    
    async def _task_soft_forget(self) -> dict[str, Any]:
        """软遗忘扫描任务"""
        result = await self.forgetter._soft_forget()
        return result
    
    async def _task_archive(self) -> dict[str, Any]:
        """归档执行任务"""
        result = await self.forgetter._archive_expired()
        return result
    
    async def _task_hard_delete(self) -> dict[str, Any]:
        """硬删除任务"""
        result = await self.forgetter._hard_delete_archived()
        return result
    
    async def _task_consistency_check(self) -> dict[str, Any]:
        """PG-Milvus 一致性检查任务"""
        if not self.milvus:
            return {"skipped": True, "reason": "Milvus not configured"}
        
        stats = {
            "checked": 0,
            "missing_in_milvus": 0,
            "orphaned_in_milvus": 0,
            "fixed": 0,
        }
        
        try:
            # 获取 PG 中的活跃记忆 ID
            pg_memories = await self.pg.get_all_active_ids(limit=10000)
            pg_ids = set(str(m) for m in pg_memories)
            stats["checked"] = len(pg_ids)
            
            # 获取 Milvus 中的向量 ID
            milvus_ids = await self.milvus.get_all_ids(limit=10000)
            milvus_id_set = set(milvus_ids)
            
            # 找出差异
            missing_in_milvus = pg_ids - milvus_id_set
            orphaned_in_milvus = milvus_id_set - pg_ids
            
            stats["missing_in_milvus"] = len(missing_in_milvus)
            stats["orphaned_in_milvus"] = len(orphaned_in_milvus)
            
            # 修复：删除 Milvus 中的孤儿向量
            if orphaned_in_milvus:
                for orphan_id in list(orphaned_in_milvus)[:100]:  # 每次最多修复100个
                    try:
                        await self.milvus.delete_memory_vector(UUID(orphan_id))
                        stats["fixed"] += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete orphan vector {orphan_id}: {e}")
            
            # 注：missing_in_milvus 需要重新生成向量，这里只记录，不自动修复
            if missing_in_milvus:
                logger.warning(
                    f"Found {len(missing_in_milvus)} memories missing in Milvus. "
                    "Consider running a full reindex."
                )
        
        except Exception as e:
            logger.error(f"Consistency check failed: {e}", exc_info=True)
            stats["error"] = str(e)
        
        return stats
    
    # ========== 手动触发接口 ==========
    
    async def run_importance_update(self) -> TaskResult:
        """手动触发重要性更新"""
        return await self._run_task(
            "importance_update_manual",
            self._task_importance_update,
            TaskConfig(),  # 使用临时配置
        )
    
    async def run_forget_cycle(self) -> ForgetResult:
        """手动触发完整遗忘周期"""
        return await self.forgetter.run_forget_cycle()
    
    async def run_consistency_check(self) -> TaskResult:
        """手动触发一致性检查"""
        return await self._run_task(
            "consistency_check_manual",
            self._task_consistency_check,
            TaskConfig(),
        )
    
    async def run_full_maintenance(self) -> dict[str, Any]:
        """运行完整维护周期"""
        results = {}
        
        # 重要性更新
        importance_result = await self.run_importance_update()
        results["importance_update"] = {
            "success": importance_result.success,
            "details": importance_result.details,
        }
        
        # 遗忘周期
        forget_result = await self.run_forget_cycle()
        results["forget_cycle"] = {
            "soft_forgotten": forget_result.soft_forgotten,
            "archived": forget_result.archived,
            "hard_deleted": forget_result.hard_deleted,
        }
        
        # 一致性检查
        consistency_result = await self.run_consistency_check()
        results["consistency_check"] = {
            "success": consistency_result.success,
            "details": consistency_result.details,
        }
        
        return results
    
    def get_status(self) -> dict[str, Any]:
        """获取 Worker 状态"""
        return {
            "running": self._running,
            "tasks": {
                "importance_update": {
                    "enabled": self.config.importance_update.enabled,
                    "interval_seconds": self.config.importance_update.interval_seconds,
                    "last_run": self.config.importance_update.last_run.isoformat() if self.config.importance_update.last_run else None,
                    "run_count": self.config.importance_update.run_count,
                    "error_count": self.config.importance_update.error_count,
                },
                "soft_forget_scan": {
                    "enabled": self.config.soft_forget_scan.enabled,
                    "interval_seconds": self.config.soft_forget_scan.interval_seconds,
                    "last_run": self.config.soft_forget_scan.last_run.isoformat() if self.config.soft_forget_scan.last_run else None,
                    "run_count": self.config.soft_forget_scan.run_count,
                    "error_count": self.config.soft_forget_scan.error_count,
                },
                "archive_execution": {
                    "enabled": self.config.archive_execution.enabled,
                    "interval_seconds": self.config.archive_execution.interval_seconds,
                    "last_run": self.config.archive_execution.last_run.isoformat() if self.config.archive_execution.last_run else None,
                    "run_count": self.config.archive_execution.run_count,
                    "error_count": self.config.archive_execution.error_count,
                },
                "hard_delete": {
                    "enabled": self.config.hard_delete.enabled,
                    "interval_seconds": self.config.hard_delete.interval_seconds,
                    "last_run": self.config.hard_delete.last_run.isoformat() if self.config.hard_delete.last_run else None,
                    "run_count": self.config.hard_delete.run_count,
                    "error_count": self.config.hard_delete.error_count,
                },
                "consistency_check": {
                    "enabled": self.config.consistency_check.enabled,
                    "interval_seconds": self.config.consistency_check.interval_seconds,
                    "last_run": self.config.consistency_check.last_run.isoformat() if self.config.consistency_check.last_run else None,
                    "run_count": self.config.consistency_check.run_count,
                    "error_count": self.config.consistency_check.error_count,
                },
            },
        }
