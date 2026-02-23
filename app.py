"""
Unified YouTube Stream API - Generates fresh cookies for every request
Single endpoint that handles everything
"""

from flask import Flask, request, jsonify
import yt_dlp
import requests
import re
import os
import json
import tempfile
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional
import uuid

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class CookieGenerator:
    """Generates fresh cookies for each request"""
    
    @staticmethod
    def get_headers() -> Dict:
        """Get realistic browser headers"""
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
    
    @staticmethod
    def generate_cookies_file() -> Optional[str]:
        """
        Generate fresh cookies and save to a temporary file in Netscape format
        Returns path to cookie file or None if failed
        """
        try:
            session = requests.Session()
            
            # Make request to YouTube
            response = session.get(
                'https://www.youtube.com',
                headers=CookieGenerator.get_headers(),
                timeout=15,
                allow_redirects=True
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch YouTube. Status: {response.status_code}")
                return None
            
            # Get cookies from session
            cookies_dict = session.cookies.get_dict()
            
            if not cookies_dict:
                logger.warning("No cookies received")
                return None
            
            # Create temporary cookie file
            temp_cookie_file = tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.txt', 
                delete=False,
                prefix='youtube_cookies_'
            )
            
            # Calculate expiration (1 year from now)
            expiration = int((datetime.now() + timedelta(days=365)).timestamp())
            
            # Write cookies in Netscape format
            with open(temp_cookie_file.name, 'w') as f:
                f.write("# Netscape HTTP Cookie File\n")
                f.write("# https://curl.se/docs/http-cookies.html\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n\n")
                
                for name, value in cookies_dict.items():
                    secure = "TRUE" if name.startswith('__Secure') else "FALSE"
                    f.write(f".youtube.com\tTRUE\t/\t{secure}\t{expiration}\t{name}\t{value}\n")
            
            logger.info(f"✅ Generated fresh cookies ({len(cookies_dict)} cookies)")
            return temp_cookie_file.name
            
        except Exception as e:
            logger.error(f"Failed to generate cookies: {e}")
            return None

def extract_video_id(url_or_id):
    """Extract YouTube video ID from URL or return the ID if already clean"""
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    
    patterns = [
        r'(?:youtube\.com\/watch\?v=)([^&]+)',
        r'(?:youtu\.be\/)([^?]+)',
        r'(?:youtube\.com\/embed\/)([^?]+)',
        r'(?:youtube\.com\/v\/)([^?]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    
    return None

def get_stream_url_with_cookies(video_id, format_id='best'):
    """
    Get stream URL using fresh cookies
    Returns dict with stream info or error
    """
    temp_cookie_file = None
    
    try:
        # Generate fresh cookies
        temp_cookie_file = CookieGenerator.generate_cookies_file()
        
        if not temp_cookie_file:
            return {
                'success': False,
                'error': 'Failed to generate cookies'
            }
        
        # Configure yt-dlp with fresh cookies
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'cookiefile': temp_cookie_file,
            'format': format_id,
            'headers': {
                'Referer': 'https://www.youtube.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            },
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'translated_subs'],
                    'player_client': ['android', 'web']
                }
            }
        }
        
        video_url = f'https://www.youtube.com/watch?v={video_id}'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"🎬 Extracting info for video {video_id} with format {format_id}")
            info = ydl.extract_info(video_url, download=False)
            
            # Find the stream URL
            stream_url = None
            format_info = None
            
            # Try to get URL from formats list
            if 'formats' in info:
                for f in info['formats']:
                    if f.get('format_id') == format_id and f.get('url'):
                        stream_url = f['url']
                        format_info = {
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext'),
                            'resolution': f.get('resolution') or f.get('format_note') or 'N/A',
                            'filesize': f.get('filesize'),
                            'vcodec': f.get('vcodec', 'none'),
                            'acodec': f.get('acodec', 'none')
                        }
                        break
            
            # If not found in formats, try the main URL
            if not stream_url and 'url' in info:
                stream_url = info['url']
                format_info = {
                    'format_id': format_id,
                    'ext': info.get('ext', 'unknown'),
                    'resolution': 'best'
                }
            
            if stream_url:
                return {
                    'success': True,
                    'stream_url': stream_url,
                    'video_id': video_id,
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'uploader': info.get('uploader'),
                    'format': format_info,
                    'view_count': info.get('view_count'),
                    'like_count': info.get('like_count'),
                    'cookies_used': True
                }
            else:
                # Get available formats
                available_formats = []
                if 'formats' in info:
                    for f in info['formats'][:10]:  # Limit to 10 formats
                        available_formats.append({
                            'format_id': f.get('format_id'),
                            'ext': f.get('ext'),
                            'resolution': f.get('resolution') or f.get('format_note') or 'N/A',
                            'has_video': f.get('vcodec') != 'none',
                            'has_audio': f.get('acodec') != 'none'
                        })
                
                return {
                    'success': False,
                    'error': f'Format {format_id} not available',
                    'available_formats': available_formats,
                    'title': info.get('title')
                }
    
    except Exception as e:
        error_msg = str(e)
        error_msg = re.sub(r'\x1b\[[0-9;]*m', '', error_msg)
        logger.error(f"Error: {error_msg}")
        return {
            'success': False,
            'error': error_msg
        }
    
    finally:
        # Clean up temporary cookie file
        if temp_cookie_file and os.path.exists(temp_cookie_file):
            try:
                os.unlink(temp_cookie_file)
                logger.debug(f"Cleaned up cookie file: {temp_cookie_file}")
            except Exception as e:
                logger.warning(f"Failed to clean up cookie file: {e}")

@app.route('/stream', methods=['GET'])
def get_stream():
    """
    Main endpoint - generates fresh cookies and returns stream URL
    Usage: /stream?id=VIDEO_ID_OR_URL&format=FORMAT_ID
    """
    # Get parameters
    video_id = request.args.get('id')
    format_id = request.args.get('format', 'best')
    
    if not video_id:
        return jsonify({
            'success': False,
            'error': 'Missing id parameter',
            'usage': {
                'endpoint': '/stream?id=VIDEO_ID&format=FORMAT_ID',
                'examples': {
                    'get_360p': '/stream?id=p7ZG_xWYLzI&format=18',
                    'get_720p': '/stream?id=p7ZG_xWYLzI&format=22',
                    'get_best': '/stream?id=p7ZG_xWYLzI&format=best',
                    'get_audio_only': '/stream?id=p7ZG_xWYLzI&format=bestaudio'
                }
            }
        }), 400
    
    # Extract clean video ID
    clean_id = extract_video_id(video_id)
    if not clean_id:
        return jsonify({
            'success': False,
            'error': 'Invalid video ID or URL'
        }), 400
    
    # Generate a request ID for tracking
    request_id = str(uuid.uuid4())[:8]
    logger.info(f"[{request_id}] Processing request for video: {clean_id}, format: {format_id}")
    
    # Get stream URL with fresh cookies
    start_time = time.time()
    result = get_stream_url_with_cookies(clean_id, format_id)
    elapsed_time = time.time() - start_time
    
    # Add metadata to response
    if result.get('success'):
        result['request_id'] = request_id
        result['processing_time'] = round(elapsed_time, 2)
        result['format_requested'] = format_id
        
        logger.info(f"[{request_id}] Success - Time: {elapsed_time:.2f}s")
        return jsonify(result)
    else:
        result['request_id'] = request_id
        result['processing_time'] = round(elapsed_time, 2)
        
        logger.warning(f"[{request_id}] Failed - {result.get('error')}")
        return jsonify(result), 404 if 'not available' in result.get('error', '') else 500

@app.route('/info', methods=['GET'])
def get_info():
    """
    Get video information without stream URL
    Usage: /info?id=VIDEO_ID_OR_URL
    """
    video_id = request.args.get('id')
    
    if not video_id:
        return jsonify({
            'success': False,
            'error': 'Missing id parameter'
        }), 400
    
    clean_id = extract_video_id(video_id)
    if not clean_id:
        return jsonify({
            'success': False,
            'error': 'Invalid video ID or URL'
        }), 400
    
    request_id = str(uuid.uuid4())[:8]
    temp_cookie_file = None
    
    try:
        # Generate fresh cookies
        temp_cookie_file = CookieGenerator.generate_cookies_file()
        
        if not temp_cookie_file:
            return jsonify({
                'success': False,
                'error': 'Failed to generate cookies'
            }), 500
        
        # Configure yt-dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'cookiefile': temp_cookie_file,
            'headers': {
                'Referer': 'https://www.youtube.com/',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }
        
        video_url = f'https://www.youtube.com/watch?v={clean_id}'
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            # Extract format information
            formats = []
            if 'formats' in info:
                for f in info['formats']:
                    formats.append({
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'resolution': f.get('resolution') or f.get('format_note') or 'N/A',
                        'filesize_mb': round(f.get('filesize', 0) / (1024 * 1024), 2) if f.get('filesize') else None,
                        'has_video': f.get('vcodec') != 'none',
                        'has_audio': f.get('acodec') != 'none',
                        'fps': f.get('fps'),
                        'vcodec': f.get('vcodec'),
                        'acodec': f.get('acodec')
                    })
            
            return jsonify({
                'success': True,
                'request_id': request_id,
                'video_id': clean_id,
                'title': info.get('title'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'description': info.get('description')[:500] + '...' if info.get('description') and len(info.get('description')) > 500 else info.get('description'),
                'thumbnail': info.get('thumbnail'),
                'upload_date': info.get('upload_date'),
                'formats': formats,
                'format_count': len(formats)
            })
    
    except Exception as e:
        error_msg = re.sub(r'\x1b\[[0-9;]*m', '', str(e))
        return jsonify({
            'success': False,
            'request_id': request_id,
            'error': error_msg
        }), 500
    
    finally:
        if temp_cookie_file and os.path.exists(temp_cookie_file):
            try:
                os.unlink(temp_cookie_file)
            except:
                pass

@app.route('/', methods=['GET'])
def home():
    """Home endpoint with usage instructions"""
    return jsonify({
        'name': 'Unified YouTube Stream API',
        'version': '1.0.0',
        'description': 'Generates fresh cookies for every request',
        'endpoints': {
            'get_stream': {
                'url': '/stream?id=VIDEO_ID&format=FORMAT_ID',
                'description': 'Get streaming URL with fresh cookies',
                'examples': {
                    '360p': '/stream?id=p7ZG_xWYLzI&format=18',
                    '720p': '/stream?id=p7ZG_xWYLzI&format=22',
                    '1080p': '/stream?id=p7ZG_xWYLzI&format=137',  # Video only
                    'best': '/stream?id=p7ZG_xWYLzI&format=best',
                    'audio': '/stream?id=p7ZG_xWYLzI&format=bestaudio'
                }
            },
            'get_info': {
                'url': '/info?id=VIDEO_ID',
                'description': 'Get video information and available formats',
                'example': '/info?id=p7ZG_xWYLzI'
            }
        },
        'common_format_ids': {
            '18': '360p (MP4)',
            '22': '720p (MP4)',
            '137': '1080p (video only)',
            '140': 'Audio only (M4A)',
            '251': 'Audio only (OPUS)',
            'best': 'Best quality',
            'bestaudio': 'Best audio only',
            'worst': 'Worst quality'
        },
        'note': 'Cookies are generated fresh for every request - no persistent cookie file needed'
    })

@app.errorhandler(404)
def not_found(e):
    return jsonify({
        'success': False,
        'error': 'Endpoint not found',
        'available_endpoints': ['/', '/stream', '/info']
    }), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Unified YouTube Stream API")
    print("=" * 60)
    print("Features:")
    print("  • Fresh cookies generated for EVERY request")
    print("  • No persistent cookie files needed")
    print("  • Automatic cleanup of temporary files")
    print("\nEndpoints:")
    print("  • GET /stream?id=VIDEO_ID&format=FORMAT")
    print("  • GET /info?id=VIDEO_ID")
    print("\nExamples:")
    print("  • http://localhost:5000/stream?id=p7ZG_xWYLzI&format=18")
    print("  • http://localhost:5000/info?id=p7ZG_xWYLzI")
    print("=" * 60)
    
    # Run the app
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
