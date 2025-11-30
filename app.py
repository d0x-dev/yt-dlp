from flask import Flask, request, send_file, jsonify
import yt_dlp
import os
import tempfile
import shutil
import logging
import re
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Cloud cookies configuration
COOKIES_URL = "https://batbin.me/raw/winnock"
COOKIES_FILE = "cookies.txt"

# Supported video qualities (for YouTube and Facebook)
SUPPORTED_QUALITIES = ['144', '240', '360', '480', '540', '720', '1080', '1440', '2160', 'best', 'worst']

def download_cloud_cookies():
    """Download cookies from cloud URL"""
    try:
        response = requests.get(COOKIES_URL)
        response.raise_for_status()
        cookies_content = response.text
        
        with open(COOKIES_FILE, "w", encoding="utf-8") as f:
            f.write(cookies_content)
        
        logger.info(f"[+] Cloud cookies downloaded and saved to {COOKIES_FILE}")
        return True
    except Exception as e:
        logger.error(f"[-] Failed to download cloud cookies: {str(e)}")
        return False

# Download cookies on startup
download_cloud_cookies()

def detect_platform(url):
    """Detect if URL is YouTube, Instagram, or Facebook"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    elif 'instagram.com' in url:
        return 'instagram'
    elif 'facebook.com' in url or 'fb.watch' in url:
        return 'facebook'
    else:
        return 'unknown'

def get_cookies_file():
    """
    Get the cloud cookies file path and ensure it exists
    """
    # If cookies file doesn't exist, try to download again
    if not os.path.exists(COOKIES_FILE):
        logger.warning("Cookies file not found, attempting to download from cloud...")
        download_cloud_cookies()
    
    # Return cookies file if it exists
    if os.path.exists(COOKIES_FILE):
        return COOKIES_FILE
    return None

def download_video_direct(video_url, quality=None):
    """
    Download video directly with specified quality using cloud cookies
    """
    platform = detect_platform(video_url)
    
    # Get cloud cookies file
    cookies_file = get_cookies_file()
    
    # Create temp directory for download
    temp_dir = tempfile.mkdtemp()
    
    ydl_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': False,
    }
    
    # Add cookies if available
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file
        logger.info(f"Using cloud cookies from: {cookies_file}")
    else:
        logger.warning("No cookies file available, proceeding without cookies")
    
    # Set format based on platform
    if platform == 'youtube':
        if not quality:
            quality = 'best'
            
        if quality not in SUPPORTED_QUALITIES:
            raise ValueError(f"Unsupported quality. Use: {', '.join(SUPPORTED_QUALITIES)}")
        
        # YouTube format selection
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif quality == 'worst':
            ydl_opts['format'] = 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst'
        else:
            # Specific quality (144, 240, 360, 480, 540, 720, 1080, etc.)
            ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
    
    elif platform == 'instagram':
        # Instagram - quality parameter is ignored, always get best
        ydl_opts['format'] = 'best'
        quality = 'best'  # For consistent response
    
    elif platform == 'facebook':
        if not quality:
            quality = 'best'
            
        if quality not in SUPPORTED_QUALITIES:
            raise ValueError(f"Unsupported quality. Use: {', '.join(SUPPORTED_QUALITIES)}")
        
        # Facebook format selection
        if quality == 'best':
            ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        elif quality == 'worst':
            ydl_opts['format'] = 'worstvideo[ext=mp4]+worstaudio[ext=m4a]/worst[ext=mp4]/worst'
        else:
            # Specific quality for Facebook
            ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
    
    else:
        raise ValueError("Unsupported platform. Only YouTube, Instagram and Facebook URLs are supported.")
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            downloaded_file = ydl.prepare_filename(info)
            
            logger.info(f"Successfully downloaded from {platform}: {info.get('title', 'Unknown')} in {quality}")
            return downloaded_file, info.get('title', 'video'), platform
            
    except Exception as e:
        # Cleanup on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Download error: {str(e)}")
        raise e

@app.route('/api/video/download', methods=['GET'])
def direct_download():
    """
    Direct download endpoint for YouTube, Instagram and Facebook
    Query parameters:
    - url: YouTube/Instagram/Facebook video URL (required)
    - quality: For YouTube/Facebook: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst (optional)
    """
    video_url = request.args.get('url')
    quality = request.args.get('quality')
    
    if not video_url:
        return "Error: Video URL parameter is required", 400
    
    platform = detect_platform(video_url)
    
    # Validate quality for YouTube and Facebook
    if platform in ['youtube', 'facebook'] and quality and quality not in SUPPORTED_QUALITIES:
        return f"Error: Unsupported quality for {platform}. Use: {', '.join(SUPPORTED_QUALITIES)}", 400
    
    # Instagram doesn't need quality parameter
    if platform == 'instagram' and quality:
        logger.info("Quality parameter ignored for Instagram")
    
    try:
        downloaded_file, video_title, platform = download_video_direct(video_url, quality)
        
        # Clean filename for download
        clean_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        if platform == 'youtube':
            filename = f"{clean_title}_{quality}p.mp4"
        elif platform == 'facebook':
            filename = f"{clean_title}_{quality}p.mp4"
        else:
            filename = f"{clean_title}_instagram.mp4"
        
        # Send file for download
        response = send_file(
            downloaded_file,
            as_attachment=True,
            download_name=filename,
            mimetype='video/mp4'
        )
        
        # Cleanup temp directory after response
        @response.call_on_close
        def cleanup():
            try:
                dir_path = os.path.dirname(downloaded_file)
                shutil.rmtree(dir_path, ignore_errors=True)
                logger.info("Cleaned up temporary files")
            except Exception as e:
                logger.error(f"Cleanup error: {str(e)}")
        
        return response
        
    except Exception as e:
        return f"Error downloading video: {str(e)}", 500

@app.route('/api/video/formats', methods=['GET'])
def available_formats():
    """
    Get available formats for a video (YouTube and Facebook)
    """
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    platform = detect_platform(video_url)
    
    if platform not in ['youtube', 'facebook']:
        return jsonify({
            'platform': platform,
            'message': 'Formats endpoint only available for YouTube and Facebook videos',
            'supported_qualities': ['best']  # Instagram always uses best quality
        })
    
    # Get cloud cookies file
    cookies_file = get_cookies_file()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
    }
    
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            formats = []
            for fmt in info.get('formats', []):
                if fmt.get('vcodec') != 'none':  # Video formats only (no audio-only)
                    formats.append({
                        'format_id': fmt.get('format_id'),
                        'resolution': f"{fmt.get('height', 'N/A')}p",
                        'ext': fmt.get('ext'),
                        'filesize': fmt.get('filesize'),
                        'format_note': fmt.get('format_note', 'N/A'),
                        'quality_label': f"{fmt.get('height', 'N/A')}p"
                    })
            
            # Get unique available qualities
            available_qualities = list(set([
                f['quality_label'] for f in formats 
                if f['quality_label'] != 'N/Ap' and f['quality_label'].replace('p', '').isdigit()
            ]))
            available_qualities.sort(key=lambda x: int(x.replace('p', '')))
            
            return jsonify({
                'platform': platform,
                'title': info.get('title'),
                'duration': info.get('duration'),
                'available_qualities': available_qualities,
                'cookies_used': bool(cookies_file),
                'formats_count': len(formats)
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/video/info', methods=['GET'])
def video_info():
    """
    Get basic video information for YouTube, Instagram and Facebook
    """
    video_url = request.args.get('url')
    
    if not video_url:
        return jsonify({'error': 'Video URL is required'}), 400
    
    platform = detect_platform(video_url)
    
    # Get cloud cookies file
    cookies_file = get_cookies_file()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': False,
    }
    
    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            response_data = {
                'platform': platform,
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
                'thumbnail': info.get('thumbnail'),
                'cookies_used': bool(cookies_file),
                'url': video_url
            }
            
            if platform in ['youtube', 'facebook']:
                response_data['supported_qualities'] = SUPPORTED_QUALITIES
            else:
                response_data['message'] = 'Instagram videos download in best available quality'
            
            return jsonify(response_data)
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/check-cookies', methods=['GET'])
def check_cookies():
    """
    Check if cookies file is available and refresh from cloud
    """
    # Option to force refresh cookies
    refresh = request.args.get('refresh', '').lower() == 'true'
    
    if refresh:
        success = download_cloud_cookies()
    else:
        success = os.path.exists(COOKIES_FILE)
    
    cookies_file = get_cookies_file()
    
    return jsonify({
        'cookies_available': bool(cookies_file),
        'cookies_file': cookies_file,
        'cloud_url': COOKIES_URL,
        'refreshed': refresh,
        'success': success
    })

@app.route('/api/refresh-cookies', methods=['POST'])
def refresh_cookies():
    """
    Force refresh cookies from cloud
    """
    success = download_cloud_cookies()
    cookies_file = get_cookies_file()
    
    return jsonify({
        'success': success,
        'cookies_file': cookies_file,
        'message': 'Cookies refreshed successfully' if success else 'Failed to refresh cookies'
    })

@app.route('/')
def home():
    return """
    <h1>Video Download API</h1>
    <p>Supports YouTube, Instagram and Facebook videos</p>
    <p><strong>Using Cloud Cookies:</strong> {}</p>
    
    <h2>Available endpoints:</h2>
    <ul>
        <li><strong>Direct Download:</strong> GET /api/video/download?url=URL&quality=720</li>
        <li><strong>Video Info:</strong> GET /api/video/info?url=URL</li>
        <li><strong>YouTube/Facebook Formats:</strong> GET /api/video/formats?url=URL</li>
        <li><strong>Check Cookies:</strong> GET /api/check-cookies</li>
        <li><strong>Refresh Cookies:</strong> POST /api/refresh-cookies</li>
    </ul>
    
    <h2>Supported Platforms:</h2>
    <ul>
        <li><strong>YouTube:</strong> Quality options: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst</li>
        <li><strong>Facebook:</strong> Quality options: 144, 240, 360, 480, 540, 720, 1080, 1440, 2160, best, worst</li>
        <li><strong>Instagram:</strong> Always downloads best available quality (quality parameter ignored)</li>
    </ul>
    
    <h2>Example URLs:</h2>
    <p><strong>YouTube:</strong> /api/video/download?url=https://youtu.be/BOF2KmrhJfc&quality=720</p>
    <p><strong>Facebook:</strong> /api/video/download?url=https://facebook.com/watch/?v=123456789&quality=720</p>
    <p><strong>Instagram:</strong> /api/video/download?url=https://instagram.com/p/ABC123/</p>
    
"""

if __name__ == '__main__':
    # Check for cookies file on startup
    cookies_file = get_cookies_file()
    if cookies_file:
        print(f"✅ Cloud cookies loaded: {cookies_file}")
    else:
        print("⚠️  No cookies file available. Age-restricted videos may not work.")
    
    print("🚀 Video Download API started - Supports YouTube, Instagram & Facebook")
    print(f"🌐 Using cloud cookies from: {COOKIES_URL}")
    app.run(debug=True, host='0.0.0.0', port=5000)
