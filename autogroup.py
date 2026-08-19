"""
autogroup.py

Bu script playlist.m3u dosyasını okuyup #EXTINF satırlarında eksik olan
`group-title` özniteliklerini basit heuristiklerle tahmin edip ekler.

Kullanım:
    python autogroup.py

Çıktı:
    playlist_grouped.m3u  <- group-title eklenmiş versiyon

Notlar:
- Heuristikler isim ve URL içindeki anahtar kelimelere dayanır. Gerekirse
  `KEYWORD_MAP` sözlüğünü düzenleyerek özel eşlemeler ekleyebilirsiniz.
- Varsayılan olarak orijinal dosyaya dokunmaz; yeni dosya üretir.
"""

import re
from pathlib import Path
from collections import Counter

INPUT = "playlist.m3u"
OUTPUT = "playlist_grouped.m3u"

# Basit anahtar kelime -> grup eşlemeleri (büyütülmüş karşılaştırma yapılır)
KEYWORD_MAP = {
    "RADYO": "Radyo",
    "RADYO7": "Radyo",
    "RADYO": "Radyo",
    "RADIO": "Radyo",
    "BEACH": "Beach",
    "PLAŽA": "Beach",
    "PLAŻA": "Beach",
    "CAM": "Cam",
    "WEBCAM": "Cam",
    "CAMERA": "Cam",
    "CAMERA": "Cam",
    "IBB": "İBB",
    "TAKSIM": "İBB",
    "MARE": "Beach",
    "ULUSAL": "Ulusal",
    "4K": "4K",
    "HD": "HD",
}

# URL tabanlı anahtar kelimeler
URL_MAP = {
    "whatsupcams": "Beach",
    "webcamera": "Beach",
    "hoktastream": "Beach",
    "beachcam": "Beach",
    "hls.ibb.gov.tr": "İBB",
    "radyotvonline": "Radyo",
    "radyotv": "Radyo",
    "ipcamera": "Cam",
}

EXTINF_RE = re.compile(r'(#EXTINF:)([^,]*)(,)(.*)')
GROUP_RE = re.compile(r'group-title\s*=\s*"([^"]*)"', re.IGNORECASE)


def collect_known_groups(lines):
    groups = []
    for l in lines:
        m = GROUP_RE.search(l)
        if m:
            groups.append(m.group(1))
    return Counter(groups)


def infer_group(name: str, url: str, known_groups: Counter) -> str:
    """Basitçe isim ve url üzerindeki anahtar kelimelere göre grup tahmini yapar."""
    if not name:
        name = ""
    u = name.upper()
    # 1) doğrudan KEYWORD_MAP içinde eşleme
    for k, v in KEYWORD_MAP.items():
        if k in u:
            return v

    # 2) bilinen gruplarla eşleştirme (örnek: 'RADYO' içeren bilinen bir grup varsa kullan)
    for g in known_groups:
        if g and g.upper() in u:
            return g

    # 3) URL tabanlı tahmin
    url_low = (url or "").lower()
    for k, v in URL_MAP.items():
        if k in url_low:
            return v

    # 4) isimde ülke/şehir/keyword anahtar eşlemeleri
    if any(token in u for token in ("SEA", "MORZE", "PLA", "PLAZA", "PLAGE", "BEACH")):
        return "Beach"

    # 5) fallback: eğer bilinen gruplardan birine benzerse kullan (örnek: "RADYO" -> "Radyo")
    for g in known_groups:
        if g and g.upper() in u:
            return g

    # 6) son çare
    return "Uncategorized"


def process(lines):
    out_lines = []
    known = collect_known_groups(lines)
    changed = 0
    total = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF"):
            total += 1
            m = EXTINF_RE.match(line)
            if m:
                attrs = m.group(2) or ""
                name = m.group(4) or ""
                # Eğer zaten group-title varsa olduğu gibi al
                if GROUP_RE.search(attrs):
                    out_lines.append(line)
                else:
                    # url genelde bir sonraki satırda
                    url = lines[i+1] if i+1 < len(lines) else ""
                    group = infer_group(name, url, known)
                    # eklemeyi attrs'ın sonuna yap, temiz boşluklar koru
                    new_attrs = attrs.rstrip() + (" " if attrs and not attrs.endswith(" ") else "") + f'group-title="{group}"'
                    new_line = f"{m.group(1)}{new_attrs}{m.group(3)}{m.group(4)}"
                    out_lines.append(new_line)
                    changed += 1
                # sonraki satırı (URL) de ekle
                if i+1 < len(lines):
                    out_lines.append(lines[i+1])
                    i += 2
                    continue
            # eğer extinf regexi eşlemezse normal ekle
            out_lines.append(line)
            i += 1
        else:
            out_lines.append(line)
            i += 1

    return out_lines, total, changed


def main():
    p = Path(INPUT)
    if not p.exists():
        print(f"Girdi dosyası bulunamadı: {INPUT}")
        return

    text = p.read_text(encoding='utf-8', errors='ignore')
    lines = text.splitlines()

    # Eğer dosya başında #EXTM3U yoksa ekleyelim
    if lines and not lines[0].startswith("#EXTM3U"):
        lines.insert(0, "#EXTM3U")

    out_lines, total, changed = process(lines)

    Path(OUTPUT).write_text('\n'.join(out_lines) + '\n', encoding='utf-8')

    print(f"Toplam EXTINF: {total}, group-title eklenen: {changed}")
    print(f"Çıktı kaydedildi: {OUTPUT}")


if __name__ == '__main__':
    main()
