"""
YouTube Operations Module
Handles API calls for listing and uploading videos
"""

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os


def get_youtube_service(credentials):
    """
    Build and return the YouTube API service object.
    
    Args:
        credentials: OAuth2 credentials object
        
    Returns:
        YouTube API service object
    """
    return build('youtube', 'v3', credentials=credentials)


def list_videos(youtube_service, max_results=10):
    """
    List videos from the authenticated user's channel.
    
    Args:
        youtube_service: YouTube API service object
        max_results: Maximum number of videos to retrieve
        
    Returns:
        List of video resources
    """
    request = youtube_service.channels().list(
        part='contentDetails',
        mine=True
    )
    response = request.execute()
    
    if 'items' in response:
        uploads_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        playlist_request = youtube_service.playlistItems().list(
            part='snippet',
            playlistId=uploads_playlist_id,
            maxResults=max_results
        )
        playlist_response = playlist_request.execute()
        return playlist_response.get('items', [])
    
    return []


def upload_video(youtube_service, video_file, title, description, category_id='22', privacy_status='private'):
    """
    Upload a video to YouTube.
    
    Args:
        youtube_service: YouTube API service object
        video_file: Path to the video file
        title: Video title
        description: Video description
        category_id: YouTube category ID (default: 22 for People & Blogs)
        privacy_status: Privacy setting ('private', 'public', or 'unlisted')
        
    Returns:
        Response from the API containing video details
    """
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy_status
        }
    }
    
    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    
    request = youtube_service.videos().insert(
        part='snippet,status',
        body=body,
        media_body=media
    )
    
    response = request.execute()
    return response


def set_thumbnail(youtube_service, video_id, thumbnail_file):
    """
    Set a custom thumbnail for a video.
    
    Args:
        youtube_service: YouTube API service object
        video_id: The ID of the video to set thumbnail for
        thumbnail_file: Path to the thumbnail image file (jpg, png, or gif)
        
    Returns:
        Response from the API
    """
    if not os.path.exists(thumbnail_file):
        raise FileNotFoundError(f"Thumbnail file not found: {thumbnail_file}")
    
    media = MediaFileUpload(thumbnail_file, mimetype='image/jpeg')
    
    request = youtube_service.thumbnails().set(
        videoId=video_id,
        media_body=media
    )
    
    response = request.execute()
    return response


def get_video_details(youtube_service, video_id):
    """
    Get detailed information about a video including duration and dimensions.
    
    Args:
        youtube_service: YouTube API service object
        video_id: The ID of the video
        
    Returns:
        Dict with video details including is_short flag
    """
    request = youtube_service.videos().list(
        part='snippet,contentDetails,status',
        id=video_id
    )
    response = request.execute()
    
    if not response.get('items'):
        return None
    
    video = response['items'][0]
    content_details = video.get('contentDetails', {})
    snippet = video.get('snippet', {})
    
    # Parse duration (ISO 8601 format like PT1M30S)
    duration_str = content_details.get('duration', 'PT0S')
    duration_seconds = parse_duration(duration_str)
    
    # Check if it's a Short (60 seconds or less, typically vertical)
    # Also check title/description for #Shorts tag
    title = snippet.get('title', '')
    description = snippet.get('description', '')
    has_shorts_tag = '#shorts' in title.lower() or '#shorts' in description.lower()
    
    is_short = duration_seconds <= 60 or has_shorts_tag
    
    return {
        'id': video_id,
        'title': title,
        'description': description,
        'duration_seconds': duration_seconds,
        'is_short': is_short,
        'category_id': snippet.get('categoryId', '22'),
        'tags': snippet.get('tags', [])
    }


def parse_duration(duration_str):
    """
    Parse ISO 8601 duration to seconds.
    
    Args:
        duration_str: Duration string like 'PT1M30S' or 'PT45S'
        
    Returns:
        Duration in seconds
    """
    import re
    
    # Remove PT prefix
    duration_str = duration_str.replace('PT', '')
    
    hours = 0
    minutes = 0
    seconds = 0
    
    # Extract hours
    hour_match = re.search(r'(\d+)H', duration_str)
    if hour_match:
        hours = int(hour_match.group(1))
    
    # Extract minutes
    min_match = re.search(r'(\d+)M', duration_str)
    if min_match:
        minutes = int(min_match.group(1))
    
    # Extract seconds
    sec_match = re.search(r'(\d+)S', duration_str)
    if sec_match:
        seconds = int(sec_match.group(1))
    
    return hours * 3600 + minutes * 60 + seconds


def get_video_playlists(youtube_service, video_id):
    """
    Get all playlists that contain a specific video (owned by authenticated user).
    
    Args:
        youtube_service: YouTube API service object
        video_id: The ID of the video
        
    Returns:
        List of playlist dicts with id and title
    """
    # First get all user's playlists
    playlists = []
    next_page_token = None
    
    while True:
        request = youtube_service.playlists().list(
            part='snippet',
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        
        for item in response.get('items', []):
            playlists.append({
                'id': item['id'],
                'title': item['snippet']['title']
            })
        
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
    
    # Check which playlists contain the video
    video_playlists = []
    
    for playlist in playlists:
        # Check if video is in this playlist
        try:
            request = youtube_service.playlistItems().list(
                part='snippet',
                playlistId=playlist['id'],
                videoId=video_id,
                maxResults=1
            )
            response = request.execute()
            
            if response.get('items'):
                video_playlists.append(playlist)
        except Exception:
            # Playlist might not be accessible or other error
            continue
    
    return video_playlists


def add_video_to_playlist(youtube_service, video_id, playlist_id):
    """
    Add a video to a playlist.
    
    Args:
        youtube_service: YouTube API service object
        video_id: The ID of the video to add
        playlist_id: The ID of the playlist
        
    Returns:
        Response from the API
    """
    body = {
        'snippet': {
            'playlistId': playlist_id,
            'resourceId': {
                'kind': 'youtube#video',
                'videoId': video_id
            }
        }
    }
    
    request = youtube_service.playlistItems().insert(
        part='snippet',
        body=body
    )
    
    response = request.execute()
    return response
