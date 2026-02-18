#!/usr/bin/env python3
"""
YouTube Automation - Main Entry Point
Automates adding intros to videos and uploading to YouTube
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from yt_automation.auth import get_service
from yt_automation.editor import stitch_intro
from yt_automation.youtube_ops import list_videos, upload_video


# Load environment variables
load_dotenv()

# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']

# Paths
CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE', 'client_secrets.json')
INTRO_VIDEO = os.getenv('INTRO_VIDEO', 'intro.mp4')
OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', 'output'))


def ensure_directories():
    """Create necessary directories if they don't exist."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    

def process_video(intro_path, video_path, output_filename=None):
    """
    Add intro to a video.
    
    Args:
        intro_path: Path to the intro video
        video_path: Path to the main video
        output_filename: Optional custom output filename
        
    Returns:
        Path to the processed video
    """
    if output_filename is None:
        video_name = Path(video_path).stem
        output_filename = f"{video_name}_with_intro.mp4"
    
    output_path = OUTPUT_DIR / output_filename
    
    print(f"Processing: {video_path}")
    print(f"Adding intro: {intro_path}")
    print(f"Output: {output_path}")
    
    stitch_intro(str(intro_path), str(video_path), str(output_path))
    
    print(f"✓ Video processed successfully: {output_path}\n")
    return output_path


def main():
    """Main entry point for the YouTube automation script."""
    
    print("=" * 60)
    print("YouTube Automation - Intro Stitcher & Uploader")
    print("=" * 60 + "\n")
    
    # Ensure required directories exist
    ensure_directories()
    
    # Check for intro video only if needed
    intro_available = os.path.exists(INTRO_VIDEO)
    if not intro_available:
        print("⚠️  Note: Intro video not found. Video processing options will be disabled.")
        print(f"   Place your intro video at '{INTRO_VIDEO}' or update INTRO_VIDEO in .env\n")
    
    # Check for client secrets
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print(f"❌ Error: Client secrets file not found at '{CLIENT_SECRETS_FILE}'")
        print(f"Please download it from Google Cloud Console")
        sys.exit(1)
    
    # Menu
    print("Select an option:")
    if intro_available:
        print("1. Process a single video (add intro)")
        print("2. Process and upload a video")
    else:
        print("1. Process a single video (add intro) - DISABLED: No intro video")
        print("2. Process and upload a video - DISABLED: No intro video")
    print("3. List your YouTube videos")
    print("4. Exit")
    
    choice = input("\nEnter your choice (1-4): ").strip()
    
    if choice == '1':
        if not intro_available:
            print("❌ This option requires an intro video. Please add one and try again.")
            sys.exit(1)
        # Process video only
        video_path = input("Enter the path to your video file: ").strip()
        if not os.path.exists(video_path):
            print(f"❌ Error: Video file not found at '{video_path}'")
            sys.exit(1)
        
        process_video(INTRO_VIDEO, video_path)
        print("✓ Done! Check the output directory for your processed video.")
    
    elif choice == '2':
        if not intro_available:
            print("❌ This option requires an intro video. Please add one and try again.")
            sys.exit(1)
        # Process and upload
        video_path = input("Enter the path to your video file: ").strip()
        if not os.path.exists(video_path):
            print(f"❌ Error: Video file not found at '{video_path}'")
            sys.exit(1)
        
        title = input("Enter video title: ").strip()
        description = input("Enter video description: ").strip()
        privacy = input("Privacy (private/unlisted/public) [private]: ").strip() or 'private'
        
        # Process video
        output_path = process_video(INTRO_VIDEO, video_path)
        
        # Authenticate and upload
        print("Authenticating with YouTube...")
        youtube = get_service(CLIENT_SECRETS_FILE, SCOPES)
        
        print(f"Uploading to YouTube...")
        response = upload_video(
            youtube,
            str(output_path),
            title,
            description,
            privacy_status=privacy
        )
        
        video_id = response['id']
        print(f"\n✓ Video uploaded successfully!")
        print(f"Video ID: {video_id}")
        print(f"URL: https://www.youtube.com/watch?v={video_id}")
    
    elif choice == '3':
        # List videos - no intro needed
        print("Authenticating with YouTube...")
        youtube = get_service(CLIENT_SECRETS_FILE, SCOPES)
        
        print("\nFetching your videos...\n")
        videos = list_videos(youtube, max_results=10)
        
        if videos:
            print(f"Found {len(videos)} recent videos:\n")
            for idx, item in enumerate(videos, 1):
                title = item['snippet']['title']
                video_id = item['snippet']['resourceId']['videoId']
                print(f"{idx}. {title}")
                print(f"   URL: https://www.youtube.com/watch?v={video_id}\n")
        else:
            print("No videos found on your channel.")
    
    elif choice == '4':
        print("Goodbye!")
        sys.exit(0)
    
    else:
        print("❌ Invalid choice. Please run the script again.")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        sys.exit(1)
