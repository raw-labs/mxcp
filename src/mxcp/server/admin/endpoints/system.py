"""
System metrics API.

Provides endpoints for collecting system-level metrics using psutil,
including CPU, memory, disk, network, and process information.
"""

import logging

import psutil  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException

from ..models import (
    CPUStatsResponse,
    DiskStatsResponse,
    MemoryStatsResponse,
    NetworkStatsResponse,
    ProcessStatsResponse,
    SystemInfoResponse,
)
from ..service import AdminService

logger = logging.getLogger(__name__)


def create_system_router(admin_service: AdminService) -> APIRouter:
    """
    Create system metrics router with admin service dependency.

    Args:
        admin_service: The admin service wrapping RAWMCP

    Returns:
        Configured APIRouter
    """
    router = APIRouter(tags=["system"], prefix="/system")

    @router.get("/info", response_model=SystemInfoResponse, summary="Get system information")
    async def get_system_info() -> SystemInfoResponse:
        """
        Get system information including OS, CPU, and memory details.

        Returns basic system information that doesn't change frequently.
        """
        try:
            boot_time = psutil.boot_time()
            cpu_count_physical = psutil.cpu_count(logical=False) or 0
            cpu_count_logical = psutil.cpu_count(logical=True) or 0
            mem = psutil.virtual_memory()

            return SystemInfoResponse(
                boot_time_seconds=int(boot_time),
                cpu_count_physical=cpu_count_physical,
                cpu_count_logical=cpu_count_logical,
                memory_total_bytes=mem.total,
            )
        except Exception as e:
            logger.error(f"[admin] Failed to get system info: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get system info: {e}") from e

    @router.get("/cpu", response_model=CPUStatsResponse, summary="Get CPU statistics")
    async def get_cpu_stats() -> CPUStatsResponse:
        """
        Get current CPU usage statistics.

        Includes overall CPU usage, per-core usage, and load averages.
        """
        try:
            # Get CPU percentages
            cpu_percent = psutil.cpu_percent(interval=0.1)
            per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)

            # Get load average (Unix only, returns 0s on Windows)
            try:
                load_1, load_5, load_15 = psutil.getloadavg()
            except (AttributeError, OSError):
                load_1 = load_5 = load_15 = 0.0

            return CPUStatsResponse(
                percent=cpu_percent,
                per_cpu_percent=per_cpu,
                load_avg_1min=load_1,
                load_avg_5min=load_5,
                load_avg_15min=load_15,
            )
        except Exception as e:
            logger.error(f"[admin] Failed to get CPU stats: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get CPU stats: {e}") from e

    @router.get("/memory", response_model=MemoryStatsResponse, summary="Get memory statistics")
    async def get_memory_stats() -> MemoryStatsResponse:
        """
        Get current memory usage statistics.

        Includes virtual memory, swap, and MXCP process memory usage.
        """
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Get MXCP process memory
            try:
                process = psutil.Process(admin_service.pid)
                mem_info = process.memory_info()
                mxcp_rss = mem_info.rss
                mxcp_vms = mem_info.vms
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                mxcp_rss = 0
                mxcp_vms = 0

            return MemoryStatsResponse(
                total_bytes=mem.total,
                available_bytes=mem.available,
                used_bytes=mem.used,
                free_bytes=mem.free,
                percent=mem.percent,
                swap_total_bytes=swap.total,
                swap_used_bytes=swap.used,
                swap_free_bytes=swap.free,
                swap_percent=swap.percent,
                mxcp_process_rss_bytes=mxcp_rss,
                mxcp_process_vms_bytes=mxcp_vms,
            )
        except Exception as e:
            logger.error(f"[admin] Failed to get memory stats: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get memory stats: {e}") from e

    @router.get("/disk", response_model=DiskStatsResponse, summary="Get disk statistics")
    async def get_disk_stats() -> DiskStatsResponse:
        """
        Get disk usage and I/O statistics.

        Includes disk space usage and I/O counters.
        """
        try:
            # Get disk usage for root partition
            usage = psutil.disk_usage("/")

            # Get disk I/O counters (may not be available on all systems)
            try:
                io_counters = psutil.disk_io_counters()
                read_bytes = io_counters.read_bytes if io_counters else 0
                write_bytes = io_counters.write_bytes if io_counters else 0
                read_count = io_counters.read_count if io_counters else 0
                write_count = io_counters.write_count if io_counters else 0
            except (AttributeError, RuntimeError):
                read_bytes = write_bytes = read_count = write_count = 0

            return DiskStatsResponse(
                total_bytes=usage.total,
                used_bytes=usage.used,
                free_bytes=usage.free,
                percent=usage.percent,
                read_bytes=read_bytes,
                write_bytes=write_bytes,
                read_count=read_count,
                write_count=write_count,
            )
        except Exception as e:
            logger.error(f"[admin] Failed to get disk stats: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get disk stats: {e}") from e

    @router.get("/network", response_model=NetworkStatsResponse, summary="Get network statistics")
    async def get_network_stats() -> NetworkStatsResponse:
        """
        Get network I/O statistics.

        Includes bytes sent/received and packet counts.
        """
        try:
            net_io = psutil.net_io_counters()

            return NetworkStatsResponse(
                bytes_sent=net_io.bytes_sent,
                bytes_recv=net_io.bytes_recv,
                packets_sent=net_io.packets_sent,
                packets_recv=net_io.packets_recv,
                errin=net_io.errin,
                errout=net_io.errout,
                dropin=net_io.dropin,
                dropout=net_io.dropout,
            )
        except Exception as e:
            logger.error(f"[admin] Failed to get network stats: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get network stats: {e}") from e

    @router.get(
        "/process", response_model=ProcessStatsResponse, summary="Get MXCP process statistics"
    )
    async def get_process_stats() -> ProcessStatsResponse:
        """
        Get detailed statistics for the MXCP process.

        Includes CPU usage, memory, threads, and file descriptors.
        """
        try:
            process = psutil.Process(admin_service.pid)

            # Get process info
            cpu_percent = process.cpu_percent(interval=0.1)
            mem_info = process.memory_info()

            # Get thread count
            num_threads = process.num_threads()

            # Get file descriptor count (Unix only)
            try:
                num_fds = process.num_fds()
            except (AttributeError, psutil.AccessDenied):
                num_fds = 0

            # Get process status
            status = process.status()

            return ProcessStatsResponse(
                pid=admin_service.pid,
                status=status,
                cpu_percent=cpu_percent,
                memory_rss_bytes=mem_info.rss,
                memory_vms_bytes=mem_info.vms,
                num_threads=num_threads,
                num_fds=num_fds,
            )
        except psutil.NoSuchProcess:
            raise HTTPException(status_code=404, detail="MXCP process not found") from None
        except psutil.AccessDenied as e:
            raise HTTPException(
                status_code=403, detail=f"Access denied to process info: {e}"
            ) from e
        except Exception as e:
            logger.error(f"[admin] Failed to get process stats: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to get process stats: {e}") from e

    return router
