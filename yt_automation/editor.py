from moviepy import VideoFileClip, concatenate_videoclips

def stitch_intro(intro_path, main_path, output_path):
    intro = VideoFileClip(intro_path)
    main = VideoFileClip(main_path)

    # Ensure they have the same resolution to avoid crashes
    # In MoviePy 2.x, use resize with height parameter
    if main.h != intro.h:
        main = main.resized(height=intro.h)

    final = concatenate_videoclips([intro, main], method="compose")
    final.write_videofile(output_path, codec="libx264", audio_codec="aac")
    intro.close()
    main.close()