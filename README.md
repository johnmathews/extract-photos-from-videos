# 📸 Photograph Extractor

## ✨ What

This script analyzes video files and extracts **photographs** with solid-color
borders, saving them as **JPEG images**.

---

## 🧐 Why

I enjoy studying photography and YouTube is a great way of studying other
photographers work.

I wanted to:
- **View photos slowly and in any order**.
- **Annotate photos** with notes about why they work or are interesting.

I used to take screenshots manually, but that was slow. This tool
automates the process! 🚀


---

## ⚙️ How It Works

1. **Input**:
   - Provide a directory containing multiple video files.
2. **Processing**:
   - The script identifies video files in the directory and processes them one
     by one.
3. **Output**:
   - Creates a subdirectory for each video (named after the video file).
   - Saves extracted photos into the corresponding subdirectory.

### 🔍 Key Details

- **Frame Selection**:
  - The tool analyzes one frame per second to save time.
- **Photo Detection**:
  - Detects photographs with a solid-color border (e.g., white). Full-frame
    photos without borders are not extracted.
- **Duplicate Avoidance**:
  - Skips duplicate photos if the same image is displayed for more than 1
    second.
  - Uses **Structural Similarity Index (SSIM)** with a default threshold of
    `0.98` (configurable).

---

## 🛠️ Dependencies

This project uses [`uv`](https://github.com/astral-sh/uv) for managing
dependencies and virtual environments.

### 🏃 Run the Tool Anywhere!

To run the script from anywhere without manually activating the virtual
environment, add the following function to your `~/.zshrc` or `~/.bashrc`:

```bash
extract_photos() {
    (source <path-to-repo>/.venv/bin/activate && uv run python <path-to-repo>/extract_photos/main.py "$@")
}
```

## 📝 Example Usage

1. Place videos in a directory, e.g., `/Users/<username>/Videos`.
2. Run the command:
   ```bash
   extract_photos "/Users/<username>/Videos"
   ```

## 💡 Ideas for Improvements

1. **Add Examples**:
   - Include example images of extracted photographs and folder structures.
   - Show screenshots of the tool in action or sample outputs.
2. **Configuration File**:
   - Add a configuration file to allow users to set parameters (e.g., frame
     rate, SSIM threshold) without editing code.
3. **Error Handling**:
   - Mention error handling mechanisms for unsupported file formats or corrupted
     videos.
4. **Logging**:
   - Highlight any logging capabilities (e.g., progress logs, skipped files).
5. **Extend Compatibility**:
   - Note supported operating systems and dependencies like OpenCV.

## 📚 License

This project is licensed under the MIT License. 📝
