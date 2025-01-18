from time import sleep


def display_progress(progress_dict, num_chunks):
    """
    Displays progress for each chunk on the console, updating in-place.
    """
    import sys

    # Print initial placeholders for each chunk
    for i in range(num_chunks):
        print(f"Chunk {i}: Initializing...")

    while True:
        # Move the cursor up by the number of chunks
        sys.stdout.write(f"\033[{num_chunks}A")  # Move up `num_chunks` lines

        # Print the progress for each chunk
        for i in range(num_chunks):

            if i % 2 == 0:  # i is even
                color_code = 32
            else:  # i is odd
                color_code = 32

            progress = progress_dict.get(
                i,
                {
                    "progress": "0.00%",
                    "time": "0:00:00/0:00:00",
                    "frames": "0/0",
                    "photos": 0,
                },
            )

            print(
                f"\033[{color_code}mChunk {i}: Photos: {progress['photos']} | {progress['progress']} | {progress['time']}\033[0m"
            )

        # Check if all chunks are complete
        if all(progress_dict.get(i, {}).get("progress") == "100.00%" for i in range(num_chunks)):
            break

        # Add a small delay for smoother updates
        sleep(1)

    # Print a newline after all progress is complete
    print()
