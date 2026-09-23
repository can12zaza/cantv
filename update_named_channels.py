#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
CAN TV - Named Channel Updater

Amaç:
- data/kanal_listesi.json içindeki sabit kanal isimlerini korur.
- categories şeklindeki JSON yapısını destekler:
    {
        "Ulusal": ["TRT 1", "ATV"],
        "Haber": ["TRT HABER", "NTV"]
    }
- sources.txt içindeki M3U kaynaklarını indirir.
- Kaynaklardaki kanal adlarını sabit kanal isimleriyle eşleştirir.
- Eşleşen URL'yi HTTP olarak kontrol eder.
- Çalışan adayları data/kanal_kaynaklari.m3u dosyasına yazar.
- data/kanal_raporu.json raporunu oluşturur.
- Aynı kanal için birden fazla çalışan kaynak varsa kalite puanı
  yüksek olanı öncelikli olarak seçer.

ÖNEMLİ:
Bu script internette rastgele yayın URL'si keşfetmez.
URL uydurmaz.
Yalnızca sources.txt içinde tanımlı kaynakları kullanır.
"""

import re
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:
    requests = None


# ============================================================
# DOSYA YOLLARI
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

CHANNELS_FILE = DATA / "kanal_listesi.json"
SOURCES_FILE = ROOT / "sources.txt"

OUT_FILE = DATA / "kanal_kaynaklari.m3u"
REPORT_FILE = DATA / "kanal_raporu.json"


# ============================================================
# AYARLAR
# ============================================================

TIMEOUT = 12

UA = "Mozilla/5.0 (compatible; CAN-TV-Channel-Matcher/2.0)"


# ============================================================
# METİN NORMALİZASYONU
# ============================================================

def norm(text):
    """
    Kanal isimlerini karşılaştırma için normalize eder.
    """

    s = (text or "").upper()

    # Türkçe karakterler
    s = s.replace("İ", "I")
    s = s.replace("Ş", "S")
    s = s.replace("Ğ", "G")
    s = s.replace("Ü", "U")
    s = s.replace("Ö", "O")
    s = s.replace("Ç", "C")

    # Parantez vb.
    s = re.sub(r"[\[\]\(\)\{\}]", " ", s)

    # Yayın kalite ifadelerini kaldır
    s = re.sub(
        r"\b(FHD|UHD|HD|SD|4K|HEVC|H265|H264)\b",
        " ",
        s
    )

    # Harf/rakam dışındakileri boşluk yap
    s = re.sub(r"[^A-Z0-9]+", " ", s)

    # Fazla boşlukları temizle
    return re.sub(r"\s+", " ", s).strip()


# ============================================================
# KANAL ALIASLARI
# ============================================================

ALIASES = {
    norm("TV 8"): {
        norm("TV8"),
        norm("TV 8"),
    },

    norm("TV 8.5"): {
        norm("TV8.5"),
        norm("TV 8.5"),
        norm("TV8 5"),
    },

    norm("HABER TÜRK"): {
        norm("HABERTURK"),
        norm("HABER TURK"),
        norm("HABER TÜRK"),
    },

    norm("NATIONAL GEOGRAPHIC"): {
        norm("NAT GEO"),
        norm("NATIONAL GEOGRAPHIC"),
        norm("NAT GEO HD"),
    },

    norm("NATIONAL GEOGRAPHIC WILD"): {
        norm("NAT GEO WILD"),
        norm("NATIONAL GEOGRAPHIC WILD"),
        norm("NATIONAL WILD"),
        norm("NAT WILD"),
    },

    norm("DISCOVERY ID"): {
        norm("DISCOVERY ID"),
        norm("ID DISCOVERY"),
    },

    norm("NR1"): {
        norm("NR1"),
        norm("NR1 TV"),
        norm("NUMBER1"),
        norm("NUMBER 1"),
    },

    norm("NR1 TÜRK"): {
        norm("NR1 TURK"),
        norm("NR1 TÜRK"),
        norm("NUMBER1 TÜRK"),
        norm("NUMBER 1 TÜRK"),
    },

    norm("DREAM TÜRK"): {
        norm("DREAM TURK"),
        norm("DREAM TÜRK"),
    },

    norm("TRT MÜZİK"): {
        norm("TRT MUZIK"),
        norm("TRT MÜZIK"),
        norm("TRT MÜZİK"),
    },

    norm("TRT DİYANET"): {
        norm("TRT DIYANET"),
        norm("TRT DİYANET"),
    },

    norm("TRT DİYANET ÇOCUK"): {
        norm("TRT DIYANET COCUK"),
        norm("TRT DİYANET ÇOCUK"),
    },

    norm("BENGÜTÜRK"): {
        norm("BENGUTURK"),
        norm("BENGÜTÜRK"),
    },

    norm("BLOOMBERG HT"): {
        norm("BLOOMBERGHT"),
        norm("BLOOMBERG HT"),
    },

    norm("EKOTÜRK"): {
        norm("EKOTURK"),
        norm("EKOTÜRK"),
    },

    norm("LIFETIME"): {
        norm("LIFE TIME"),
        norm("LIFETIME"),
    },

    norm("KRAL FM"): {
        norm("KRAL FM"),
        norm("KIRAL FM"),
    },

    norm("KRAL POP"): {
        norm("KRAL POP"),
        norm("KIRAL POP"),
    },
}


# ============================================================
# SOURCES.TXT OKU
# ============================================================

def read_sources():
    """
    sources.txt içindeki URL'leri okur.
    """

    if not SOURCES_FILE.exists():
        print(f"[HATA] sources.txt bulunamadı: {SOURCES_FILE}")
        return []

    sources = []

    for line in SOURCES_FILE.read_text(
        encoding="utf-8",
        errors="ignore"
    ).splitlines():

        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        sources.append(line)

    return sources


# ============================================================
# KAYNAK İNDİR
# ============================================================

def fetch(url):
    """
    M3U kaynağını indirir.
    """

    if requests:
        response = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": UA},
        )

        response.raise_for_status()

        return response.text

    request = Request(
        url,
        headers={"User-Agent": UA}
    )

    with urlopen(request, timeout=TIMEOUT) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


# ============================================================
# M3U PARSE
# ============================================================

def parse_m3u(text, source):
    """
    M3U içinden:

    display
    url
    EXTINF
    source

    bilgilerini çıkarır.
    """

    lines = text.splitlines()

    result = []

    i = 0

    while i < len(lines):

        line = lines[i].strip()

        if line.startswith("#EXTINF"):

            ext = line

            url = ""

            j = i + 1

            # Boş satırları geç
            while j < len(lines) and not lines[j].strip():
                j += 1

            # URL satırı
            if (
                j < len(lines)
                and not lines[j].strip().startswith("#")
            ):
                url = lines[j].strip()

            if url:

                parts = ext.split(",", 1)

                if len(parts) == 2:
                    display = parts[1].strip()
                else:
                    display = "KANAL"

                result.append(
                    (
                        display,
                        url,
                        ext,
                        source
                    )
                )

            i = j + 1

        else:
            i += 1

    return result


# ============================================================
# KANAL EŞLEŞTİRME
# ============================================================

def channel_match(target, candidate):
    """
    Sabit kanal adı ile kaynak kanal adını karşılaştırır.
    """

    a = norm(target)
    b = norm(candidate)

    if not a or not b:
        return False

    # Tam eşleşme
    if a == b:
        return True

    # Alias eşleşmesi
    if b in ALIASES.get(a, set()):
        return True

    if a in ALIASES.get(b, set()):
        return True

    # Boşluksuz eşleşme
    a_compact = re.sub(r"\s+", "", a)
    b_compact = re.sub(r"\s+", "", b)

    if a_compact == b_compact:
        return True

    return False


# ============================================================
# YAYIN KONTROLÜ
# ============================================================

def check_stream(url):
    """
    URL'nin HTTP olarak cevap verip vermediğini kontrol eder.
    """

    try:

        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return False, "unsupported-scheme"

        if requests:

            response = requests.get(
                url,
                timeout=TIMEOUT,
                headers={"User-Agent": UA},
                stream=True,
                allow_redirects=True,
            )

            status = response.status_code

            ok = 200 <= status < 400

            response.close()

            return ok, f"http-{status}"

        request = Request(
            url,
            headers={"User-Agent": UA}
        )

        with urlopen(
            request,
            timeout=TIMEOUT
        ) as response:

            status = getattr(
                response,
                "status",
                200
            )

            return (
                200 <= status < 400,
                f"http-{status}"
            )

    except Exception as e:

        return False, type(e).__name__


# ============================================================
# KALİTE PUANI
# ============================================================

def quality_score(text):
    """
    Kanal isminden yayın kalitesi puanı çıkarır.

    4K / UHD = 4
    FHD      = 3
    HD       = 2
    SD       = 1
    Diğer    = 0
    """

    u = (text or "").upper()

    if "4K" in u:
        return 4

    if "UHD" in u:
        return 4

    if "FHD" in u or "FULL HD" in u:
        return 3

    if "HD" in u:
        return 2

    if "SD" in u:
        return 1

    return 0


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # KANAL LİSTESİNİ OKU
    # --------------------------------------------------------

    if not CHANNELS_FILE.exists():

        print(
            f"[HATA] Kanal listesi bulunamadı: "
            f"{CHANNELS_FILE}"
        )

        return 1

    try:

        channels = json.loads(
            CHANNELS_FILE.read_text(
                encoding="utf-8"
            )
        )

    except Exception as e:

        print(
            f"[HATA] kanal_listesi.json okunamadı: {e}"
        )

        return 1

    # JSON yapısının dictionary olması gerekiyor
    if not isinstance(channels, dict):

        print(
            "[HATA] kanal_listesi.json yapısı hatalı."
        )

        print(
            "Beklenen yapı: "
            '{"Ulusal": ["TRT 1", "ATV"]}'
        )

        return 1

    # --------------------------------------------------------
    # KAYNAKLARI OKU
    # --------------------------------------------------------

    sources = read_sources()

    if not sources:

        print(
            "[HATA] sources.txt içinde kaynak bulunamadı."
        )

        return 1

    # --------------------------------------------------------
    # KAYNAKLARDAN KANALLARI TOPLA
    # --------------------------------------------------------

    candidates = []

    source_errors = []

    for src in sources:

        try:

            text = fetch(src)

            parsed = parse_m3u(
                text,
                src
            )

            candidates.extend(parsed)

            print(
                f"[OK] kaynak: {src}"
            )

            print(
                f"     bulunan kayıt: {len(parsed)}"
            )

        except Exception as e:

            source_errors.append(
                {
                    "source": src,
                    "error": str(e),
                }
            )

            print(
                f"[HATA] kaynak: {src} -> {e}"
            )

    # --------------------------------------------------------
    # TOPLAM GERÇEK KANAL SAYISI
    # --------------------------------------------------------

    total_channels = 0

    for category, channel_names in channels.items():

        if isinstance(channel_names, list):

            total_channels += len(channel_names)

    # --------------------------------------------------------
    # ÇIKTI VE RAPOR
    # --------------------------------------------------------

    out = [
        "#EXTM3U"
    ]

    report = {

        "total_channels": total_channels,

        "matched": 0,

        "not_found": 0,

        "source_errors": source_errors,

        "channels": []
    }

    # --------------------------------------------------------
    # KANALLARI KATEGORİ KATEGORİ İŞLE
    # --------------------------------------------------------

    for category, channel_names in channels.items():

        # Güvenlik kontrolü
        if not isinstance(
            channel_names,
            list
        ):
            continue

        print()
        print(
            f"========== {category} =========="
        )

        for name in channel_names:

            # Kanal adı string değilse atla
            if not isinstance(name, str):
                continue

            name = name.strip()

            if not name:
                continue

            # ------------------------------------------------
            # AD EŞLEŞMELERİNİ BUL
            # ------------------------------------------------

            matches = [
                x
                for x in candidates
                if channel_match(
                    name,
                    x[0]
                )
            ]

            # ------------------------------------------------
            # KALİTEYE GÖRE SIRALA
            # ------------------------------------------------

            matches.sort(
                key=lambda x: quality_score(x[0]),
                reverse=True
            )

            # ------------------------------------------------
            # ÇALIŞAN KAYNAK BUL
            # ------------------------------------------------

            chosen = None

            attempts = []

            for (
                display,
                url,
                ext,
                source
            ) in matches:

                ok, reason = check_stream(
                    url
                )

                attempts.append(
                    {
                        "url": url,
                        "source": source,
                        "ok": ok,
                        "reason": reason,
                        "display": display,
                        "quality": quality_score(
                            display
                        ),
                    }
                )

                if ok:

                    chosen = (
                        display,
                        url,
                        ext,
                        source
                    )

                    break

            # ------------------------------------------------
            # ÇALIŞAN KAYNAK BULUNDU
            # ------------------------------------------------

            if chosen:

                (
                    display,
                    url,
                    ext,
                    source
                ) = chosen

                # Kaynaktaki ismi kullanma.
                # Bizim sabit kanal ismimizi kullan.
                out.append(
                    f'#EXTINF:-1 '
                    f'tvg-name="{name}" '
                    f'group-title="{category}",'
                    f'{name}'
                )

                out.append(url)

                report["matched"] += 1

                report["channels"].append(
                    {
                        "name": name,
                        "category": category,
                        "status": "working",
                        "url": url,
                        "source": source,
                        "matched_display": display,
                        "quality": quality_score(
                            display
                        ),
                        "attempts": attempts,
                    }
                )

                print(
                    f"[ÇALIŞIYOR] "
                    f"{name} <- {url}"
                )

            # ------------------------------------------------
            # KAYNAK BULUNAMADI
            # ------------------------------------------------

            else:

                report["not_found"] += 1

                report["channels"].append(
                    {
                        "name": name,
                        "category": category,
                        "status": "not_found",
                        "attempts": attempts,
                    }
                )

                if matches:

                    print(
                        f"[BULUNDU AMA ÇALIŞMIYOR] "
                        f"{name}"
                    )

                else:

                    print(
                        f"[BULUNAMADI] "
                        f"{name}"
                    )

    # --------------------------------------------------------
    # ÇIKTI KLASÖRÜNÜ GARANTİ ET
    # --------------------------------------------------------

    DATA.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # M3U DOSYASINI YAZ
    # --------------------------------------------------------

    OUT_FILE.write_text(
        "\n".join(out) + "\n",
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # RAPORU YAZ
    # --------------------------------------------------------

    REPORT_FILE.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # SONUÇ
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("CAN TV - Named Channel Updater")
    print("=" * 60)

    print(
        f"Toplam kanal       : "
        f"{report['total_channels']}"
    )

    print(
        f"Eşleşen / çalışan  : "
        f"{report['matched']}"
    )

    print(
        f"Bulunamayan        : "
        f"{report['not_found']}"
    )

    print(
        f"Kaynak hatası      : "
        f"{len(report['source_errors'])}"
    )

    print(
        f"Çıktı              : "
        f"{OUT_FILE}"
    )

    print(
        f"Rapor              : "
        f"{REPORT_FILE}"
    )

    print("=" * 60)

    return 0


# ============================================================
# PROGRAM BAŞLANGICI
# ============================================================

if __name__ == "__main__":
    raise SystemExit(main())
