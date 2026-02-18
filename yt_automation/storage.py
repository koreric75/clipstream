"""
Storage Management Module
Handles folder size monitoring and cleanup operations
"""

import os
import shutil
from pathlib import Path


# Storage threshold in bytes (1 GB)
STORAGE_WARNING_THRESHOLD = 1 * 1024 * 1024 * 1024  # 1 GB


def get_folder_size(folder_path):
    """
    Calculate the total size of a folder in bytes.
    
    Args:
        folder_path: Path to the folder
        
    Returns:
        Total size in bytes
    """
    folder = Path(folder_path)
    if not folder.exists():
        return 0
    
    total_size = 0
    for file in folder.rglob('*'):
        if file.is_file():
            total_size += file.stat().st_size
    
    return total_size


def format_size(size_bytes):
    """
    Format bytes into human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Human-readable string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} PB"


def check_storage_warning(folder_path, threshold=STORAGE_WARNING_THRESHOLD):
    """
    Check if folder size is approaching the threshold and warn user.
    
    Args:
        folder_path: Path to the folder to check
        threshold: Warning threshold in bytes (default: 1 GB)
        
    Returns:
        True if warning was triggered, False otherwise
    """
    folder = Path(folder_path)
    if not folder.exists():
        return False
    
    current_size = get_folder_size(folder_path)
    threshold_percent = (current_size / threshold) * 100
    
    if current_size >= threshold:
        print(f"\n⚠️  WARNING: '{folder}' has exceeded storage threshold!")
        print(f"   Current size: {format_size(current_size)} (over {format_size(threshold)} limit)")
        print(f"   Consider cleaning up to free storage space.\n")
        return True
    elif threshold_percent >= 80:
        print(f"\n⚠️  WARNING: '{folder}' is approaching storage limit!")
        print(f"   Current size: {format_size(current_size)} ({threshold_percent:.1f}% of {format_size(threshold)})")
        print(f"   Consider cleaning up soon.\n")
        return True
    
    return False


def cleanup_folder(folder_path, confirm=True):
    """
    Clean up all files in a folder.
    
    Args:
        folder_path: Path to the folder to clean
        confirm: Whether to ask for user confirmation
        
    Returns:
        Number of files deleted, total bytes freed
    """
    folder = Path(folder_path)
    if not folder.exists():
        print(f"Folder '{folder}' does not exist.")
        return 0, 0
    
    # Get current size
    current_size = get_folder_size(folder_path)
    files = list(folder.glob('*'))
    file_count = len([f for f in files if f.is_file()])
    
    if file_count == 0:
        print(f"Folder '{folder}' is already empty.")
        return 0, 0
    
    print(f"\n🗑️  Cleanup: '{folder}'")
    print(f"   Files: {file_count}")
    print(f"   Size: {format_size(current_size)}")
    
    if confirm:
        response = input("   Delete all files? (y/N): ").strip().lower()
        if response != 'y':
            print("   Cleanup cancelled.")
            return 0, 0
    
    # Delete files
    deleted_count = 0
    for item in files:
        try:
            if item.is_file():
                item.unlink()
                deleted_count += 1
            elif item.is_dir():
                shutil.rmtree(item)
                deleted_count += 1
        except Exception as e:
            print(f"   Failed to delete {item.name}: {e}")
    
    print(f"   ✓ Deleted {deleted_count} items, freed {format_size(current_size)}")
    return deleted_count, current_size


def cleanup_processed_videos(output_folder, download_folder=None, confirm=True):
    """
    Clean up processed videos from output and optionally downloads folder.
    
    Args:
        output_folder: Path to output folder
        download_folder: Optional path to downloads folder
        confirm: Whether to ask for user confirmation
        
    Returns:
        Total files deleted, total bytes freed
    """
    total_deleted = 0
    total_freed = 0
    
    # Check storage warning first
    check_storage_warning(output_folder)
    if download_folder:
        check_storage_warning(download_folder)
    
    # Clean output folder
    deleted, freed = cleanup_folder(output_folder, confirm)
    total_deleted += deleted
    total_freed += freed
    
    # Clean downloads folder if specified
    if download_folder:
        deleted, freed = cleanup_folder(download_folder, confirm)
        total_deleted += deleted
        total_freed += freed
    
    if total_deleted > 0:
        print(f"\n✓ Total cleanup: {total_deleted} items, {format_size(total_freed)} freed")
    
    return total_deleted, total_freed


def storage_status(folders):
    """
    Print storage status for multiple folders.
    
    Args:
        folders: List of folder paths to check
    """
    print("\n📊 Storage Status:")
    print("-" * 40)
    
    total_size = 0
    for folder in folders:
        folder_path = Path(folder)
        if folder_path.exists():
            size = get_folder_size(folder)
            total_size += size
            print(f"   {folder_path.name}/: {format_size(size)}")
        else:
            print(f"   {folder_path.name}/: (not found)")
    
    print("-" * 40)
    print(f"   Total: {format_size(total_size)}")
    
    # Check if any are over threshold
    for folder in folders:
        check_storage_warning(folder)
