"""Normalize media explicitly identified by Qzone's feed responses."""

from typing import Any

import bs4


def _first_url(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_feed_media(msg: dict[str, Any]) -> tuple[list[str], list[str], bool]:
    images: list[str] = []
    videos: list[str] = []
    has_video = bool(msg.get("video"))
    video_keys = (
        "play_url", "playUrl", "video_url", "videoUrl", "download_url",
        "downloadUrl", "url3", "url",
    )
    for pic in msg.get("pic") or []:
        if not isinstance(pic, dict):
            continue
        info = pic.get("video_info")
        if not isinstance(info, dict):
            info = pic.get("videoInfo")
        if isinstance(info, dict):
            has_video = True
            url = _first_url(info, video_keys)
            if url:
                videos.append(url)
            continue
        url = _first_url(pic, ("url2", "url3", "url1", "smallurl"))
        if url:
            images.append(url)
    for video in msg.get("video") or []:
        if isinstance(video, dict):
            url = _first_url(video, video_keys)
            if url:
                videos.append(url)
    html = msg.get("html")
    if isinstance(html, str) and html:
        soup = bs4.BeautifulSoup(html, "html.parser")
        for video_element in soup.select("div.img-box.f-video-wrap.play"):
            has_video = True
            url = _first_url(video_element.attrs, video_keys)
            if url:
                videos.append(url)
    return list(dict.fromkeys(images)), list(dict.fromkeys(videos)), has_video
