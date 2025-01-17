import os
import tempfile
from extract_photos.batch_processor import process_videos_in_directory

def test_process_videos_in_directory():
    # Create temporary directories
    with tempfile.TemporaryDirectory() as input_dir, tempfile.TemporaryDirectory() as output_dir:
        # Mock video files
        open(os.path.join(input_dir, "video1.mp4"), "w").close()
        open(os.path.join(input_dir, "video2.mkv"), "w").close()

        # Call the function
        process_videos_in_directory(input_dir, output_dir)

        # Check output directories
        assert os.path.exists(os.path.join(output_dir, "video1"))
        assert os.path.exists(os.path.join(output_dir, "video2"))
