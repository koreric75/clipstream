"""
YouTube Operations Module
Handles API calls for listing and uploading videos
"""

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


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
