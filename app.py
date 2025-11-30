import os
import requests
import subprocess
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

app = FastAPI()

COOKIES_URL = "https://batbin.me/raw/winnock"
COOKIES_FILE = "cookies.txt"

def download_cookies():
    cookies = requests.get(COOKIES_URL).text
    with open(COOKIES_FILE, "w", encoding="utf-8") as f:
        f.write(cookies)
    print("[+] Cookies Updated")

download_cookies()


@app.get("/download")
async def download_video(url: str = Query(...)):
    os.makedirs("downloads", exist_ok=True)

    output_template = "downloads/%(title)s.%(ext)s"

    cmd = [
        "yt-dlp",
        "--cookies", COOKIES_FILE,
        "-f", "bv*+ba/b",
        "-o", output_template,
        url
    ]

    print("[+] Downloading:", url)
    subprocess.run(cmd)

    files = os.listdir("downloads")
    if not files:
        return {"error": "Download failed"}

    file_path = os.path.join("downloads", files[0])

    return FileResponse(
        file_path,
        media_type="video/mp4",
        filename=files[0]
    )


# 🔥 RENDER FIX — Start Uvicorn Server
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)
