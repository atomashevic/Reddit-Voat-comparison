"""System resource monitoring utilities for large-scale data processing.

Provides functions to monitor memory, disk space, CPU usage, and file sizes.
Designed for use on remote machines with limited resources when processing
large Parquet files (5-50+ GB).

Usage:
    # As a module
    from scripts.resource_monitor import get_memory_status, check_disk_space
    
    ms = get_memory_status()
    if ms["percent"] > 85:
        logging.warning(f"High memory usage: {ms['percent']:.1f}%")
    
    # As a CLI tool
    python scripts/resource_monitor.py --interval 5 --watch
"""

import argparse
import logging
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    logging.warning("psutil not available, using /proc/meminfo fallback")


def get_memory_status() -> Dict[str, float]:
    """Get current memory usage statistics.
    
    Returns:
        Dictionary with keys:
            - total: Total memory in GB
            - available: Available memory in GB
            - used: Used memory in GB
            - percent: Memory usage percentage (0-100)
            - free: Free memory in GB (same as available)
    
    Uses psutil if available, otherwise falls back to /proc/meminfo.
    """
    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        return {
            "total": mem.total / (1024**3),
            "available": mem.available / (1024**3),
            "used": mem.used / (1024**3),
            "percent": mem.percent,
            "free": mem.available / (1024**3),
        }
    
    # Fallback to /proc/meminfo
    try:
        with open("/proc/meminfo", "r") as f:
            meminfo = {}
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    value = int(parts[1])
                    meminfo[key] = value
        
        # Convert from KB to GB
        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
        used_kb = total_kb - available_kb
        
        total_gb = total_kb / (1024**2)
        available_gb = available_kb / (1024**2)
        used_gb = used_kb / (1024**2)
        percent = (used_kb / total_kb * 100) if total_kb > 0 else 0.0
        
        return {
            "total": total_gb,
            "available": available_gb,
            "used": used_gb,
            "percent": percent,
            "free": available_gb,
        }
    except (FileNotFoundError, IOError, KeyError) as e:
        logging.error(f"Failed to read memory info: {e}")
        return {
            "total": 0.0,
            "available": 0.0,
            "used": 0.0,
            "percent": 0.0,
            "free": 0.0,
        }


def get_disk_status(path: str = ".") -> Dict[str, float]:
    """Get disk space statistics for a given path.
    
    Args:
        path: Path to check disk space for (default: current directory)
    
    Returns:
        Dictionary with keys:
            - total: Total disk space in GB
            - used: Used disk space in GB
            - free: Free disk space in GB
            - percent: Disk usage percentage (0-100)
    """
    try:
        stat = shutil.disk_usage(path)
        total_gb = stat.total / (1024**3)
        used_gb = stat.used / (1024**3)
        free_gb = stat.free / (1024**3)
        percent = (stat.used / stat.total * 100) if stat.total > 0 else 0.0
        
        return {
            "total": total_gb,
            "used": used_gb,
            "free": free_gb,
            "percent": percent,
        }
    except (OSError, PermissionError) as e:
        logging.error(f"Failed to get disk usage for {path}: {e}")
        return {
            "total": 0.0,
            "used": 0.0,
            "free": 0.0,
            "percent": 0.0,
        }


def get_cpu_status() -> Dict[str, float]:
    """Get CPU usage statistics.
    
    Returns:
        Dictionary with keys:
            - percent: CPU usage percentage (0-100)
            - count: Number of CPU cores
            - per_cpu: List of per-CPU percentages (if available)
    
    Requires psutil. Returns empty dict if psutil not available.
    """
    if not HAS_PSUTIL:
        return {"percent": 0.0, "count": 0, "per_cpu": []}
    
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
        
        return {
            "percent": cpu_percent,
            "count": cpu_count,
            "per_cpu": per_cpu,
        }
    except Exception as e:
        logging.error(f"Failed to get CPU status: {e}")
        return {"percent": 0.0, "count": 0, "per_cpu": []}


def check_file_size(file_path: str, warn_gb: float = 10.0) -> float:
    """Check file size and warn if large.
    
    Args:
        file_path: Path to file to check
        warn_gb: Size threshold in GB to trigger warning (default: 10.0)
    
    Returns:
        File size in GB
    
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    size_bytes = os.path.getsize(file_path)
    size_gb = size_bytes / (1024**3)
    
    if size_gb > warn_gb:
        logging.warning(f"Large file detected: {size_gb:.1f} GB - {file_path}")
    
    return size_gb


def check_disk_space(path: str, required_gb: float = 1.0) -> bool:
    """Check if sufficient disk space is available.
    
    Args:
        path: Path to check disk space for
        required_gb: Required free space in GB (default: 1.0)
    
    Returns:
        True if sufficient space available, False otherwise
    """
    disk = get_disk_status(path)
    available_gb = disk["free"]
    
    if available_gb < required_gb:
        logging.error(
            f"Insufficient disk space: {available_gb:.1f} GB available, "
            f"{required_gb:.1f} GB required at {path}"
        )
        return False
    
    return True


def check_memory_threshold(
    warn_percent: float = 85.0, abort_percent: float = 95.0
) -> Tuple[bool, Dict[str, float]]:
    """Check memory usage against thresholds.
    
    Args:
        warn_percent: Warning threshold percentage (default: 85.0)
        abort_percent: Abort threshold percentage (default: 95.0)
    
    Returns:
        Tuple of (should_abort, memory_status_dict)
    """
    ms = get_memory_status()
    percent = ms.get("percent", 0.0)
    
    if percent > abort_percent:
        logging.error(
            f"Memory usage too high: {percent:.1f}% (abort threshold: {abort_percent}%)"
        )
        return True, ms
    
    if percent > warn_percent:
        logging.warning(
            f"High memory usage: {percent:.1f}% (warning threshold: {warn_percent}%)"
        )
    
    return False, ms


def format_resource_summary() -> str:
    """Format a human-readable summary of all system resources.
    
    Returns:
        Multi-line string with memory, disk, and CPU status
    """
    mem = get_memory_status()
    disk = get_disk_status()
    cpu = get_cpu_status()
    
    lines = [
        "=== System Resource Status ===",
        f"Memory: {mem['used']:.1f} GB / {mem['total']:.1f} GB "
        f"({mem['percent']:.1f}%) - {mem['available']:.1f} GB available",
        f"Disk:   {disk['used']:.1f} GB / {disk['total']:.1f} GB "
        f"({disk['percent']:.1f}%) - {disk['free']:.1f} GB free",
    ]
    
    if cpu.get("count", 0) > 0:
        lines.append(
            f"CPU:    {cpu['percent']:.1f}% ({cpu['count']} cores)"
        )
    
    return "\n".join(lines)


def monitor_continuously(
    interval: int = 5,
    warn_memory: float = 85.0,
    abort_memory: float = 95.0,
    warn_disk: float = 90.0,
    abort_disk: float = 95.0,
) -> None:
    """Continuously monitor system resources and log warnings.
    
    Args:
        interval: Seconds between checks (default: 5)
        warn_memory: Memory warning threshold percentage (default: 85.0)
        abort_memory: Memory abort threshold percentage (default: 95.0)
        warn_disk: Disk warning threshold percentage (default: 90.0)
        abort_disk: Disk abort threshold percentage (default: 95.0)
    """
    logging.info(f"Starting continuous monitoring (interval: {interval}s)")
    logging.info(f"Memory thresholds: warn={warn_memory}%, abort={abort_memory}%")
    logging.info(f"Disk thresholds: warn={warn_disk}%, abort={abort_disk}%")
    
    try:
        while True:
            # Check memory
            should_abort, mem = check_memory_threshold(warn_memory, abort_memory)
            if should_abort:
                logging.error("Aborting due to high memory usage")
                sys.exit(1)
            
            # Check disk
            disk = get_disk_status()
            if disk["percent"] > abort_disk:
                logging.error(
                    f"Aborting due to high disk usage: {disk['percent']:.1f}%"
                )
                sys.exit(1)
            elif disk["percent"] > warn_disk:
                logging.warning(
                    f"High disk usage: {disk['percent']:.1f}% "
                    f"(warning threshold: {warn_disk}%)"
                )
            
            # Log status
            logging.info(format_resource_summary())
            
            time.sleep(interval)
    except KeyboardInterrupt:
        logging.info("Monitoring stopped by user")


def main() -> None:
    """CLI entry point for resource monitoring."""
    parser = argparse.ArgumentParser(
        description="Monitor system resources (memory, disk, CPU)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Seconds between checks in watch mode (default: 5)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor resources",
    )
    parser.add_argument(
        "--warn-memory",
        type=float,
        default=85.0,
        help="Memory warning threshold percentage (default: 85.0)",
    )
    parser.add_argument(
        "--abort-memory",
        type=float,
        default=95.0,
        help="Memory abort threshold percentage (default: 95.0)",
    )
    parser.add_argument(
        "--warn-disk",
        type=float,
        default=90.0,
        help="Disk warning threshold percentage (default: 90.0)",
    )
    parser.add_argument(
        "--abort-disk",
        type=float,
        default=95.0,
        help="Disk abort threshold percentage (default: 95.0)",
    )
    parser.add_argument(
        "--check-path",
        type=str,
        help="Check disk space for specific path",
    )
    parser.add_argument(
        "--required-gb",
        type=float,
        default=1.0,
        help="Required free space in GB for --check-path (default: 1.0)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    args = parser.parse_args()
    
    # Configure logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    # Check specific path if requested
    if args.check_path:
        if check_disk_space(args.check_path, args.required_gb):
            logging.info(
                f"Sufficient disk space available at {args.check_path}"
            )
            sys.exit(0)
        else:
            sys.exit(1)
    
    # Watch mode or single check
    if args.watch:
        monitor_continuously(
            interval=args.interval,
            warn_memory=args.warn_memory,
            abort_memory=args.abort_memory,
            warn_disk=args.warn_disk,
            abort_disk=args.abort_disk,
        )
    else:
        # Single check
        print(format_resource_summary())


if __name__ == "__main__":
    main()

