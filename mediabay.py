import asyncio
import os
import time
import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, HTMLResponse

app = FastAPI()

# ============ SOZLAMALAR ============
MEDIABAY_API = "https://api.mediabay.uz/v2/channels/listRadio"
PLAYLIST_CACHE_TTL = 5  # Keshlash vaqti

# Xotirada radiolar ro'yxati va tokenni saqlash
_radio_cache = {"data": [], "ts": 0}
_radio_lock = asyncio.Lock()

# Token indeksini boshqarish uchun
_active_token_index = {"value": 0}
_token_lock = asyncio.Lock()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

# 1. Mediabay API'dan radiolarni tortib kelish
async def fetch_mediabay_radios():
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(MEDIABAY_API, headers=HEADERS)
            resp.raise_for_status()
            result = resp.json()
            if result.get("status") == "ok":
                return result.get("data", [])
    except Exception as e:
        print(f"API xatosi: {e}")
    return []

# 2. Har 5 sekundda tokenni (yoki ma'lumotni) yangilab turuvchi fon jarayoni
async def token_rotation_loop():
    while True:
        await asyncio.sleep(5)
        channels = await fetch_mediabay_radios()
        if channels:
            async with _radio_lock:
                _radio_cache["data"] = channels
                _radio_cache["ts"] = time.time()
            async with _token_lock:
                # Har 5 sekundda qaysidir tokenni aylantirish yoki indeksni surish
                _active_token_index["value"] += 1

@app.on_event("startup")
async def startup_event():
    # Dastlabki yuklab olish
    channels = await fetch_mediabay_radios()
    _radio_cache["data"] = channels
    _radio_cache["ts"] = time.time()
    # 5 sekundlik siklni ishga tushirish
    async asyncio.create_task(token_rotation_loop())

# 3. Asosiy M3U Playlist generatsiya qilish
@app.get("/")
@app.get("/playlist.m3u")
@app.get("/playlist.m3u8")
async def playlist(request: Request):
    async with _radio_lock:
        channels = _radio_cache["data"]
    
    if not channels:
        # Agar kesh bo'sh bo'lsa qayta urinib ko'ramiz
        channels = await fetch_mediabay_radios()

    base_url = str(request.base_url).rstrip("/")
    
    m3u_lines = ["#EXTM3U"]
    for ch in channels:
        name = ch.get("name", "Radio")
        logo = ch.get("logo", "")
        media_host = "https://media.mediabay.uz" # API'dan kelgan mediaHost
        logo_url = f"{media_host}{logo}" if logo.startswith("/") else logo
        preview_url = ch.get("preview", "")
        
        ch_id = ch.get("id")
        
        # Har bir kanal uchun o'zimizning proxy orqali M3U havolasini tuzamiz
        m3u_lines.append(f'#EXTINF:-1 tvg-logo="{logo_url}",{name}')
        m3u_lines.append(f"{base_url}/stream/{ch_id}.m3u8")

    content = "\n".join(m3u_lines)
    return Response(
        content=content, 
        media_type="application/vnd.apple.mpegurl", 
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-cache"}
    )

# 4. Alohida kanal uchun oqimni yo'naltirish (Proxy & Token Injector)
@app.get("/stream/{ch_id}.m3u8")
async def stream_channel(ch_id: int, request: Request):
    async with _radio_lock:
        channels = _radio_cache["data"]
    
    target_channel = None
    for ch in channels:
        if ch.get("id") == ch_id:
            target_channel = ch
            break
            
    if not target_channel:
        return PlainTextResponse("Kanal topilmadi", status_code=404)
        
    preview_url = target_channel.get("preview", "")
    
    # Mediabay asl streamiga so'rov yuborish va tokenni uzatish
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(preview_url, headers=HEADERS)
            resp.raise_for_status()
            data = resp.content
            content_type = resp.headers.get("content-type", "application/vnd.apple.mpegurl")
            
            # Agar `.m3u8` playlist qaytsa, ichidagi segment havolalarini to'g'rilash mumkin
            return Response(content=data, media_type=content_type, headers={"Access-Control-Allow-Origin": "*"})
    except Exception as e:
        return PlainTextResponse(f"Streamni ochishda xatolik: {e}", status_code=502)

@app.get("/health")
async def health():
    return {"status": "ok", "channels_count": len(_radio_cache["data"])}