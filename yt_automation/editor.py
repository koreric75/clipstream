from moviepy import VideoFileClip, concatenate_videoclips
from moviepy.video.fx import FadeIn, FadeOut
import os


def is_vertical_video(video_path):
    """
    Check if a video is vertical (9:16 or similar).
    
    Args:
        video_path: Path to the video file
        
    Returns:
        True if video is vertical (height > width), False otherwise
    """
    clip = VideoFileClip(video_path)
    is_vertical = clip.h > clip.w
    clip.close()
    return is_vertical


def get_video_aspect_ratio(video_path):
    """
    Get the aspect ratio of a video.
    
    Args:
        video_path: Path to the video file
        
    Returns:
        Tuple of (width, height, aspect_ratio)
    """
    clip = VideoFileClip(video_path)
    w, h = clip.w, clip.h
    aspect = w / h
    clip.close()
    return w, h, aspect


def select_intro_for_video(main_video_path, intro_horizontal, intro_vertical):
    """
    Select the appropriate intro based on the main video's aspect ratio.
    
    Args:
        main_video_path: Path to the main video
        intro_horizontal: Path to 16:9 intro
        intro_vertical: Path to 9:16 intro (for Shorts)
        
    Returns:
        Path to the appropriate intro video
    """
    if is_vertical_video(main_video_path):
        # Use vertical intro if available, otherwise fall back to horizontal
        if os.path.exists(intro_vertical):
            return intro_vertical
        else:
            return intro_horizontal
    else:
        return intro_horizontal


def stitch_intro(intro_path, main_path, output_path, fade_duration=0.5):
    """
    Stitch an intro video to the beginning of a main video.
    
    Args:
        intro_path: Path to the intro video
        main_path: Path to the main video
        output_path: Path for the output video
        fade_duration: Duration of fade transition in seconds
    """
    intro = VideoFileClip(intro_path)
    main = VideoFileClip(main_path)

    # Ensure they have the same resolution to avoid crashes
    # In MoviePy 2.x, use resize with height parameter
    if main.h != intro.h:
        main = main.resized(height=intro.h)
    
    # Also ensure same width (for vertical videos, width might differ)
    if main.w != intro.w:
        main = main.resized(width=intro.w)

    # Add fade transition: fade out intro to black, fade in main video from black
    intro = intro.with_effects([FadeOut(fade_duration)])
    main = main.with_effects([FadeIn(fade_duration)])

    final = concatenate_videoclips([intro, main], method="compose")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    intro.close()
    main.close()


def stitch_intro_auto(main_path, output_path, intro_horizontal='intro.mp4', 
                       intro_vertical='intro_short.mp4', fade_duration=0.5):
    """
    Automatically select and stitch the appropriate intro based on video orientation.
    
    Args:
        main_path: Path to the main video
        output_path: Path for the output video
        intro_horizontal: Path to 16:9 intro
        intro_vertical: Path to 9:16 intro (for Shorts)
        fade_duration: Duration of fade transition in seconds
        
    Returns:
        The intro_path that was used
    """
    # Select appropriate intro
    intro_path = select_intro_for_video(main_path, intro_horizontal, intro_vertical)
    
    # Stitch videos
    stitch_intro(intro_path, main_path, output_path, fade_duration)
    
    return intro_path