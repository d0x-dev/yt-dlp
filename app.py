import os
import requests
import subprocess
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

app = FastAPI()

COOKIES_URL = "https://batbin.me/raw/winnock"
COOKIES_FILE = "cookies.txt"

# Download cookies on startup
def download_cookies():
    cookies = requests.get(COOKIES_URL).text
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(cookies)
    print("[+] Cookies Updated")

download_cookies()


@app.get("/download")
async def download_video(url: str = Query(..., description="YouTube Video URL")):
    # Make temp folder
    os.makedirs("downloads", exist_ok=True)

    # Output file name with yt-dlp template
    output_path = "downloads/%(title)s.%(ext)s"

    command = [
        "yt-dlp",
        "--cookies", COOKIES_FILE,
        "-f", "bv*+ba/b",
        "-o", output_path,
        url
    ]

    print("[+] Downloading:", url)
    subprocess.run(command)

    # Find downloaded file
    files = os.listdir("downloads")
    if not files:
        return {"error": "Download failed"}

    file_path = os.path.join("downloads", files[0])

    # Send video file as direct download
    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=files[0]
    )
