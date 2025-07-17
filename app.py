import os
import tempfile
import cv2
import assemblyai as aai
import yt_dlp as ytdl
from pydub import AudioSegment
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv # To load environment variables
import re # For sanitizing filenames

# Load environment variables from .env file
# Ensure your .env file is in the root directory (your_project_name/)
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure AssemblyAI with your API key from environment variable
# It's better practice to load from .env than hardcoding in the script
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in .env file. Please set it.")


# Create a temporary directory for processed files
TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'temp')
os.makedirs(TEMP_DIR, exist_ok=True)

# Define supported audio and video extensions for validation
SUPPORTED_VIDEO_EXTS = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv')
SUPPORTED_AUDIO_EXTS = ('.mp3', '.wav', '.flac', '.ogg', '.aac', '.m4a', '.opus')
ALL_SUPPORTED_EXTS = SUPPORTED_VIDEO_EXTS + SUPPORTED_AUDIO_EXTS

def sanitize_filename(filename):
    """Sanitize filename to remove characters that might cause path issues."""
    sanitized = re.sub(r'[^\w\s\.-]', '', filename)
    sanitized = re.sub(r'\s+', '_', sanitized)
    return sanitized

def extract_audio_with_pydub(media_path):
    """Extract audio from a video/audio file and save it as a WAV file."""
    audio_path = tempfile.mktemp(suffix=".wav", dir=TEMP_DIR)
    try:
        audio = AudioSegment.from_file(media_path)
        audio = audio.set_channels(1) # Ensure mono
        audio = audio.set_frame_rate(16000) # Ensure 16kHz sample rate for AAI
        audio.export(audio_path, format="wav")
        app.logger.info(f"Extracted audio to: {audio_path}")
        return audio_path
    except Exception as e:
        app.logger.error(f"Error extracting audio with pydub from {media_path}: {e}", exc_info=True)
        if os.path.exists(audio_path):
            os.remove(audio_path)
        raise Exception(f"Failed to extract audio from media file: {e}")

def transcribe_audio_or_video(file_path):
    """Transcribe audio using AssemblyAI."""
    transcriber = aai.Transcriber()
    try:
        # AssemblyAI can handle various audio/video formats directly,
        # but extracting to WAV first for consistency with pydub can be safer.
        # However, the AssemblyAI SDK is intelligent enough to process many video/audio formats.
        # We ensure audio is extracted if it's a video file, otherwise use the path directly.
        transcript = transcriber.transcribe(file_path)
        if transcript.status == aai.TranscriptStatus.error:
            error_message = transcript.error or "Unknown transcription error."
            raise Exception(f"AssemblyAI transcription failed: {error_message}")
        app.logger.info("Transcription successful.")
        return transcript.text
    except Exception as e:
        app.logger.error(f"Error transcribing with AssemblyAI from {file_path}: {e}", exc_info=True)
        raise Exception(f"Failed to transcribe media with AssemblyAI: {e}")

def download_online_media(url):
    """Download media file from URL using yt-dlp."""
    output_dir = TEMP_DIR
    output_template = os.path.join(output_dir, "%(id)s_%(title)s.%(ext)s")

    ydl_opts = {
        'format': 'best', # Select the best quality available
        'outtmpl': output_template,
        'noplaylist': True,
        'keepvideo': True, # Keep the downloaded file for serving
        'writethumbnail': False,
        'quiet': True,
        'no_warnings': True,
        'cachedir': False, # Prevent caching issues
    }

    downloaded_file_path = None
    try:
        with ytdl.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            # The most reliable way to get the actual downloaded file name from yt-dlp
            downloaded_file_path = info_dict.get('_filename') or info_dict.get('filepath')

            if not downloaded_file_path or not os.path.exists(downloaded_file_path):
                # Fallback: Search for recent files in TEMP_DIR if explicit path not found
                app.logger.warning(f"Explicit downloaded file path not found: {downloaded_file_path}. Searching temp directory.")
                recent_files = sorted(
                    [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR)],
                    key=os.path.getctime, reverse=True
                )
                for f in recent_files:
                    if os.path.isfile(f) and f.lower().endswith(ALL_SUPPORTED_EXTS):
                        app.logger.info(f"Found via fallback: {f}")
                        downloaded_file_path = f
                        break
                if not downloaded_file_path:
                    raise Exception("Failed to find downloaded media file after extraction.")

            app.logger.info(f"Successfully downloaded: {downloaded_file_path}")
            return downloaded_file_path

    except ytdl.utils.DownloadError as e:
        app.logger.error(f"yt-dlp download error for {url}: {e}", exc_info=True)
        raise Exception(f"Failed to download media from URL. It might be private, geo-restricted, or unsupported. yt-dlp Error: {e}")
    except Exception as e:
        app.logger.error(f"Generic error during online media download for {url}: {e}", exc_info=True)
        raise Exception(f"An unexpected error occurred during media download: {e}")

@app.route('/api/process-media', methods=['POST'])
def process_media():
    transcript_text = None
    video_output_url = None
    processed_filepath = None # Path to the file that was either uploaded or downloaded
    audio_for_transcription_path = None # Path to the audio file sent to AssemblyAI

    try:
        is_url = request.form.get('is_url') == 'true'

        if is_url:
            url_input = request.form.get('url_input')
            if not url_input or not url_input.startswith(('http://', 'https://')):
                return jsonify({"error": "Please provide a valid URL."}), 400

            app.logger.info(f"Processing URL: {url_input}")
            processed_filepath = download_online_media(url_input)
            video_output_url = f'/media/{os.path.basename(processed_filepath)}'

        else: # File Upload
            if 'file_input' not in request.files:
                return jsonify({"error": "No file part in the request."}), 400
            file = request.files['file_input']
            if file.filename == '':
                return jsonify({"error": "No selected file."}), 400

            original_filename = file.filename
            file_extension = os.path.splitext(original_filename)[1].lower()
            if file_extension not in ALL_SUPPORTED_EXTS:
                return jsonify({"error": f"Unsupported file format: {file_extension}. Please upload a common audio or video file."}), 400

            sanitized_filename = sanitize_filename(original_filename)
            processed_filepath = os.path.join(TEMP_DIR, sanitized_filename)
            file.save(processed_filepath)
            app.logger.info(f"Uploaded file saved to: {processed_filepath}")

            video_output_url = f'/media/{os.path.basename(processed_filepath)}'

        # Determine if audio extraction is needed for transcription by AssemblyAI
        # While AAI can often handle video directly, pydub extraction can ensure
        # consistent audio format for AAI, and handles cases where AAI might
        # prefer a specific audio stream.
        if processed_filepath.lower().endswith(SUPPORTED_VIDEO_EXTS):
            audio_for_transcription_path = extract_audio_with_pydub(processed_filepath)
        elif processed_filepath.lower().endswith(SUPPORTED_AUDIO_EXTS):
            audio_for_transcription_path = processed_filepath # Already an audio file
        else:
            return jsonify({"error": "File type could not be determined for transcription."}), 500

        # Transcribe the extracted audio
        transcript_text = transcribe_audio_or_video(audio_for_transcription_path)

        return jsonify({
            "video_path": video_output_url, # Frontend will use this to play the media
            "transcript": transcript_text
        }), 200

    except Exception as e:
        app.logger.error(f"API Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up temporary audio file used for transcription if it's different from the main processed file
        # The main processed_filepath (uploaded/downloaded media) is kept so it can be served for playback.
        if audio_for_transcription_path and \
           audio_for_transcription_path != processed_filepath and \
           os.path.exists(audio_for_transcription_path):
            try:
                os.remove(audio_for_transcription_path)
                app.logger.info(f"Cleaned up temp audio file: {audio_for_transcription_path}")
            except OSError as e:
                app.logger.error(f"Error cleaning up temp audio file {audio_for_transcription_path}: {e}")


# Route to serve static media files from the temp directory
@app.route('/media/<filename>')
def serve_media(filename):
    try:
        # Security: Prevent directory traversal by only serving the basename
        base_filename = os.path.basename(filename)
        return send_from_directory(TEMP_DIR, base_filename)
    except Exception as e:
        app.logger.error(f"Error serving media file {filename}: {e}")
        return jsonify({"error": "Media file not found or accessible."}), 404

# Route to serve the main frontend HTML file
@app.route('/')
def serve_index():
    return send_from_directory('../frontend', 'index.html')

# Route to serve other static frontend files (CSS, JS)
@app.route('/<path:path>')
def serve_static_frontend(path):
    # Security: Ensure paths don't go outside the frontend directory
    # os.path.abspath is for normalization; then check if it's within expected dir
    abs_frontend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../frontend'))
    abs_requested_path = os.path.abspath(os.path.join(abs_frontend_path, path))

    if not abs_requested_path.startswith(abs_frontend_path):
        return "Forbidden", 403 # Path traversal attempt

    return send_from_directory('../frontend', path)


if __name__ == '__main__':
    # For local development, use Flask's built-in development server.
    # In production, you would typically use a WSGI server like Gunicorn or uWSGI.
    app.run(debug=True, port=5000)
    # Alternatively, for more stable local development:
    # from werkzeug.serving import run_simple
    # run_simple('127.0.0.1', 5000, app, use_reloader=True, use_debugger=True)