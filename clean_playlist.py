import re
from pathlib import Path

SRC = "playlist.m3u"
OUT = "playlist_clean.m3u"

# Regex'leri bir kez derle
QUALITY_PATTERN = re.compile(r"\b(4K|UHD|FHD|FULL ?HD|HD|SD)\b")
DASH_PATTERN = re.compile(r"[-_]+")
SPACE_PATTERN = re.compile(r"\s+")

priority = {"4K": 4, "UHD": 4, "FHD": 3, "FULL HD": 3, "HD": 2, "SD": 1}
PRIORITY_PATTERN = re.compile("|".join(re.escape(k) for k in priority.keys()))

def norm(name: str) -> str:
    name = name.upper()
    name = QUALITY_PATTERN.sub("", name)
    name = DASH_PATTERN.sub(" ", name)
    name = SPACE_PATTERN.sub(" ", name).strip()
    return name

def score(name: str) -> int:
    matches = PRIORITY_PATTERN.findall(name.upper())
    return max((priority[m] for m in matches), default=0)

lines = Path(SRC).read_text(encoding="utf-8", errors="replace").splitlines()

seen_url = set()
best = {}

i = 0
while i < len(lines) - 1:
    if lines[i].startswith("#EXTINF"):
        extinf = lines[i]
        url = lines[i + 1].strip()
        if not url.startswith(("http://", "https://", "rtmp://", "rtsp://")):
            i += 2
            continue
        name = extinf.split(",", 1)[1].strip() if "," in extinf else "KANAL"
        if url in seen_url:
            i += 2
            continue
        seen_url.add(url)

        key = norm(name)
        item = (score(name), extinf, url)  # ← Orijinal name ile score hesapla

        if key not in best or item[0] > best[key][0]:
            best[key] = item
        i += 2
    else:
        i += 1

with open(OUT, "w", encoding="utf-8") as f:
    f.write("#EXTM3U\n")
    for _, extinf, url in best.values():
        f.write(extinf + "\n" + url + "\n")

print(f"Yazılan kanal: {len(best)}")
