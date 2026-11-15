"""YouTube Data API v3 calls: resumable video upload, thumbnail, captions."""

import random
import time
from pathlib import Path

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

RETRIABLE_STATUS = {500, 502, 503, 504}
MAX_RETRIES = 8
CHUNK_SIZE = 16 * 1024 * 1024

# Approximate quota units per call (default project quota is 10,000/day).
QUOTA = {"videos.insert": 1600, "thumbnails.set": 50, "captions.insert": 400, "channels.list": 1}


def _backoff(attempt: int) -> None:
    time.sleep(min(2 ** attempt + random.random(), 64))


def upload_video(service, video: Path, body: dict, log=print) -> str:
    media = MediaFileUpload(str(video), chunksize=CHUNK_SIZE, resumable=True)
    request = service.videos().insert(part="snippet,status", body=body, media_body=media)

    response, attempt, last_pct = None, 0, -1
    while response is None:
        try:
            status, response = request.next_chunk()
            attempt = 0
            if status:
                pct = int(status.progress() * 100)
                if pct // 10 != last_pct // 10:
                    log(f"    {pct}%")
                    last_pct = pct
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                raise
            attempt = _retry_or_raise(attempt, e, log)
        except (ConnectionError, TimeoutError, OSError) as e:
            attempt = _retry_or_raise(attempt, e, log)

    if "id" not in response:
        raise RuntimeError(f"Unexpected upload response: {response}")
    return response["id"]


def _retry_or_raise(attempt: int, err: Exception, log) -> int:
    attempt += 1
    if attempt > MAX_RETRIES:
        raise err
    log(f"    retry {attempt}/{MAX_RETRIES} after error: {err}")
    _backoff(attempt)
    return attempt


def set_thumbnail(service, video_id: str, thumbnail: Path) -> None:
    service.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail))).execute()


def insert_caption(service, video_id: str, caption: Path, language: str, name: str = "") -> None:
    body = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
    service.captions().insert(
        part="snippet", body=body, media_body=MediaFileUpload(str(caption)), sync=False
    ).execute()
