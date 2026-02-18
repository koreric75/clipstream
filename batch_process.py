#!/usr/bin/env python3
"""
Batch Process Videos from Playlist
Downloads videos, adds intro, and re-uploads to YouTube
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv

from yt_automation.auth import get_service
from yt_automation.editor import stitch_intro
from yt_automation.youtube_ops import upload_video

# Load environment variables
load_dotenv()

# Configuration
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE', 'client_secrets.json')
INTRO_VIDEO = os.getenv('INTRO_VIDEO', 'intro.mp4')
DOWNLOAD_DIR = Path('downloads')
OUTPUT_DIR = Path('output')


def ensure_directories():
    """Create necessary directories."""
    DOWNLOAD_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)


def get_playlist_videos(playlist_url, limit=None):
    """
    Get video metadata from a YouTube playlist.
    
    Args:
        playlist_url: URL of the YouTube playlist
        limit: Maximum number of videos to retrieve
        
    Returns:
        List of video dictionaries with id, title, description
    """
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--flat-playlist',
        '--print', '%(id)s',
        '--print', '%(title)s',
        '--print', '%(description)s',
        '--print', '---END---',
        playlist_url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')
    
    videos = []
    i = 0
    while i < len(lines):
        if i + 3 < len(lines):
            video_id = lines[i].strip()
            title = lines[i + 1].strip()
            description = lines[i + 2].strip() if lines[i + 2].strip() != 'NA' else ''
            
            # Skip private/unavailable videos
            if video_id and title and '[Private video]' not in title and '[Unavailable]' not in title:
                videos.append({
                    'id': video_id,
                    'title': title,
                    'description': description
                })
            i += 4  # Move past ---END---
        else:
            break
    
    # Remove duplicates based on video ID
    seen_ids = set()
    unique_videos = []
    for v in videos:
        if v['id'] not in seen_ids:
            seen_ids.add(v['id'])
            unique_videos.append(v)
    
    if limit:
        unique_videos = unique_videos[:limit]
    
    return unique_videos


def download_video(video_id, output_path):
    """
    Download a video from YouTube.
    
    Args:
        video_id: YouTube video ID
        output_path: Path to save the downloaded video
        
    Returns:
        True if successful, False otherwise
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-f', 'best[height<=1080]',
        '-o', str(output_path),
        '--no-playlist',
        url
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def process_batch(playlist_url, limit=6, privacy_status='private'):
    """
    Process a batch of videos from a playlist.
    
    Args:
        playlist_url: URL of the YouTube playlist
        limit: Number of videos to process
        privacy_status: Privacy status for uploaded videos
    """
    print("=" * 60)
    print("Batch Video Processor")
    print("=" * 60 + "\n")
    
    ensure_directories()
    
    # Check for intro video
    if not os.path.exists(INTRO_VIDEO):
        print(f"❌ Error: Intro video not found at '{INTRO_VIDEO}'")
        sys.exit(1)
    
    # Get playlist videos
    print(f"📋 Fetching playlist videos (limit: {limit})...")
    videos = get_playlist_videos(playlist_url, limit)
    
    if not videos:
        print("❌ No videos found in playlist")
        sys.exit(1)
    
    print(f"✓ Found {len(videos)} videos to process:\n")
    for i, v in enumerate(videos, 1):
        print(f"  {i}. {v['title'][:50]}{'...' if len(v['title']) > 50 else ''}")
    print()
    
    # Authenticate with YouTube
    print("🔐 Authenticating with YouTube...")
    youtube = get_service(CLIENT_SECRETS_FILE, SCOPES)
    print("✓ Authenticated\n")
    
    # Process each video
    results = []
    for i, video in enumerate(videos, 1):
        print(f"\n{'='*60}")
        print(f"Processing video {i}/{len(videos)}: {video['title'][:40]}...")
        print("=" * 60)
        
        video_id = video['id']
        title = video['title']
        description = video['description'] or f"Re-uploaded with intro. Original: https://youtu.be/{video_id}"
        
        # Download
        download_path = DOWNLOAD_DIR / f"{video_id}.mp4"
        print(f"⬇️  Downloading...")
        
        if download_path.exists():
            print(f"   (Using cached download)")
        else:
            if not download_video(video_id, download_path):
                print(f"❌ Failed to download video {video_id}")
                results.append({'video': video, 'status': 'download_failed'})
                continue
        
        print(f"✓ Downloaded: {download_path}")
        
        # Add intro
        output_path = OUTPUT_DIR / f"{video_id}_with_intro.mp4"
        print(f"🎬 Adding intro...")
        
        try:
            stitch_intro(str(INTRO_VIDEO), str(download_path), str(output_path))
            print(f"✓ Intro added: {output_path}")
        except Exception as e:
            print(f"❌ Failed to add intro: {e}")
            results.append({'video': video, 'status': 'processing_failed', 'error': str(e)})
            continue
        
        # Upload
        print(f"⬆️  Uploading to YouTube (privacy: {privacy_status})...")
        
        try:
            response = upload_video(
                youtube,
                str(output_path),
                title,
                description,
                privacy_status=privacy_status
            )
            
            new_video_id = response['id']
            new_url = f"https://www.youtube.com/watch?v={new_video_id}"
            print(f"✓ Uploaded successfully!")
            print(f"   New URL: {new_url}")
            
            results.append({
                'video': video,
                'status': 'success',
                'new_id': new_video_id,
                'new_url': new_url
            })
            
        except Exception as e:
            print(f"❌ Failed to upload: {e}")
            results.append({'video': video, 'status': 'upload_failed', 'error': str(e)})
    
    # Summary
    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 60 + "\n")
    
    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] != 'success']
    
    print(f"✓ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}\n")
    
    if successful:
        print("Uploaded Videos:")
        for r in successful:
            print(f"  - {r['video']['title'][:40]}...")
            print(f"    {r['new_url']}")
        print()
    
    if failed:
        print("Failed Videos:")
        for r in failed:
            print(f"  - {r['video']['title'][:40]}... ({r['status']})")
            if 'error' in r:
                print(f"    Error: {r['error']}")
    
    return results


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch process videos from YouTube playlist')
    parser.add_argument('playlist_url', help='YouTube playlist URL')
    parser.add_argument('--limit', '-l', type=int, default=6, help='Number of videos to process (default: 6)')
    parser.add_argument('--privacy', '-p', choices=['private', 'unlisted', 'public'], 
                        default='private', help='Privacy status for uploads (default: private)')
    
    args = parser.parse_args()
    
    try:
        process_batch(args.playlist_url, args.limit, args.privacy)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        sys.exit(1)
