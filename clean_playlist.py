# download_playlists.py
import re
from pathlib import Path

SOURCES_FILE = "sources.txt"
OUTPUT_FILE = "playlist.m3u"

def download_playlists():
    """sources.txt'den tüm playlist URL'lerini indir ve birleştir"""
    
    sources = Path(SOURCES_FILE).read_text(encoding="utf-8").strip().split("\n")
    
    combined = "#EXTM3U\n"
    
    for url in sources:
        url = url.strip()
        if not url:
            continue
            
        print(f"İndiriliyor: {url}")
        
        try:
            response = requests.get(url, timeout=10)
            response.encoding = 'utf-8'
            
            # URL'den gelen playlist'i birleştir
            content = response.text
            if content.startswith("#EXTM3U"):
                content = "\n".join(content.split("\n")[1:])  # İlk satırı atla
            
            combined += content + "\n"
            print(f"✓ Başarılı")
            
        except Exception as e:
            print(f"✗ Hata: {e}")
    
    # Birleştirilmiş playlist'i kaydet
    Path(OUTPUT_FILE).write_text(combined, encoding="utf-8")
    print(f"\n✓ {OUTPUT_FILE} kaydedildi")

if __name__ == "__main__":
    download_playlists()
