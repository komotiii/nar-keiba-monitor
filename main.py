import re, os, json, requests, time, pykakasi
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from tabulate import tabulate
from termcolor import colored
import pygame
from charset_normalizer import detect

kks = pykakasi.kakasi()
WIN_RATE_THRESHOLD = 0.8
ODDS_MIN, ODDS_MAX = 1.1, 1.3
SITE_IDS = [[36, "水沢"],[44, "大井"]]
#笠松 投票締切時刻は、発走時刻の2分前です。
WAIT_SEC = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}
TODAY = datetime.now()
YEAR, MONTH, DAY = TODAY.year, TODAY.month, TODAY.day
JSON_PATH = rf"C:\Users\yakim\Documents\github\nar-keiba-monitor\datas\{MONTH:02d}{DAY:02d}.json"
PIC_MP = r"C:\Users\yakim\Desktop\ALLDATA\MP3\fic.mp3"
FTN_MP = r"C:\Users\yakim\Desktop\ALLDATA\MP3\futon.mp3"
headers = ["No", "Horse", "WinOdds", "OddsMin", "OddsMax", "WinRate", "PastRanks"]

print("\n","\n=== Program start ===\n")

def play_sound(path, volume=1.0):
    pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.set_volume(volume)  # 0.0 to 1.0
    pygame.mixer.music.play()

    # 再生が終わるまで待機
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

def countdown(sec):
    print("\n")
    for remaining in range(sec, 0, -1):
        print(f"\rWaiting {remaining:2d} sec   ", end="", flush=True)
        time.sleep(1)
    print(" " * 30)

def to_romaji(text):
    result = kks.convert(text)
    return ''.join([item['hepburn'] for item in result])

def get_race_id(site_id: int, race_num: int) -> int:
    base_id = int(f"{YEAR:04d}{site_id:02d}{MONTH:02d}{DAY:02d}")
    return base_id * 100 + race_num

def fetch_html(url: str):
    res = requests.get(url, headers=HEADERS, timeout=15)
    # netkeiba (NAR) pages are commonly encoded in EUC-JP.
    # Use it first to avoid mojibake in race text and horse names.
    try:
        res.content.decode("euc_jp")
        res.encoding = "euc_jp"
    except Exception:
        enc = detect(res.content).get("encoding") or res.apparent_encoding or "utf-8"
        res.encoding = enc
    ret = BeautifulSoup(res.text, "html.parser")
    return ret

def extract_race_info(race_id: int):
    url = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"
    soup = fetch_html(url)

    # race start time / race rule
    time_tag = soup.select_one('div.RaceData01')
    if not time_tag:
        raise ValueError("No race data block")

    race_text = time_tag.get_text(" ", strip=True)
    m = re.search(r'(\d{1,2})[:：](\d{2})\s*発走', race_text)
    if not m:
        # Fallback for pages where decoding makes the "発走" token unreliable.
        m = re.search(r'(\d{1,2})[:：](\d{2})', race_text)
    if not m:
        raise ValueError("No race start time")

    # Handle format variants like ダ1400m, ダ1,400m, 芝1200m
    rule_match = re.search(r'(ダ|芝)\s*[0-9,]{3,5}\s*m', race_text)
    rule = rule_match.group(0).replace(" ", "") if rule_match else "N/A"

    race_time = datetime(YEAR, MONTH, DAY, int(m.group(1)), int(m.group(2)))
    # get horse ranks
    horse_data = {}
    has_excellent = False
    for tr in soup.select('tr.HorseList'):
        no_tag = tr.select_one('td.Waku')
        horse_no = no_tag.text.strip()
        ranks = [
            span.text.strip()
            for td in tr.select('td.Past')
            for span in [td.select_one('div.Data_Item div.Data01 span.Num')]
            if span
        ]
        top3 = sum(1 for r in ranks if r in ['1', '2', '3'])
        wr = top3 / max(5, len(ranks)) if ranks else 0
        if wr >= WIN_RATE_THRESHOLD:
            has_excellent = True
        horse_data[horse_no] = {
            "rank_ranks": ranks,
            "win_rate": wr
        }
    horse_data["__has_excellent__"] = has_excellent
    return race_time, horse_data ,rule

def extract_odds_info(race_id: int):
    url = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
    print(url)
    soup = fetch_html(url)
    odds_info = {}

    odds_rows = soup.select("table.RaceOdds_HorseList_Table tr")[1:]

    for row in odds_rows:
        horse_no_tag = row.select_one("td.Waku")
        horse_name_tag = row.select_one("td.Horse_Name a")
        odds_tags = row.select("td.Odds span.Odds")
        if horse_no_tag and horse_name_tag and len(odds_tags) == 2:
            horse_no = horse_no_tag.text.strip()
            horse_name = horse_name_tag.text.strip()
            odds_text = odds_tags[0].text.strip()
            place_text = odds_tags[1].text.strip()

            if odds_text in ["取消", "返還"] or place_text in ["取消", "返還"]:
                win_odds = None
                odds_min = None
                odds_max = None
            else:
                try:
                    win_odds = float(odds_text)
                    place_range = place_text.split(" - ")
                    odds_min = float(place_range[0])
                    odds_max = float(place_range[1])
                except Exception as e:
                    print(f"[ERROR parsing odds] Horse {horse_no}: {e}")
                    win_odds = odds_min = odds_max = None

            odds_info[horse_no] = {
                "horse_name": horse_name,
                "win_odds": win_odds,
                "odds_min": odds_min,
                "odds_max": odds_max,
            }
    return odds_info


def build_daily_data():
    data = []
    for site_id, site_name in SITE_IDS:
        for race_num in range(1, 13):
            race_id = get_race_id(site_id, race_num)
            try:
                race_time, horse_info,rule = extract_race_info(race_id)
                data.append({
                    "race_datetime": race_time,
                    "race_id": race_id,
                    "site_name": site_name,
                    "race_num": race_num,
                    "rule": rule,
                    "horse_info": horse_info
                })
                print(f"Processed {site_name} {race_num}R at {race_time}")
            except Exception as e:
                print(f"[ERROR] {site_name} {race_num}R: {e}")

    data.sort(key=lambda x: x["race_datetime"])

    # Create a copy for saving to JSON
    data_to_save = []
    for d in data:
        d_copy = d.copy()
        if isinstance(d_copy["race_datetime"], datetime):
            d_copy["race_datetime"] = d_copy["race_datetime"].isoformat()
        data_to_save.append(d_copy)

    # Save the string-converted copy
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    print(f"Saved data to {JSON_PATH}")
    return data


# Load JSON (fallback to fresh fetch when file is empty/stale)
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("Data loaded from JSON.", "\n")
    for d in data:
        d["race_datetime"] = datetime.fromisoformat(d["race_datetime"])
    if not data:
        print("Cached JSON is empty. Rebuilding from web...\n")
        data = build_daily_data()
else:
    data = build_daily_data()


def fetch_odds_periodically(race_id: int, target_time: datetime, detail):
    notified_5min = False
    notified_2min = False
    while True:
        now = datetime.now()
        now_time = now.time()
        print(detail)
        time_to_start = (target_time - now).total_seconds()
        if not notified_5min and 0 < time_to_start <= 300:
            print("【Notify】Betting closes in 3 minutes.")
            #play_sound(FTN_MP, volume=1)
            notified_5min = True
        if not notified_2min and 0 < time_to_start <= 120:
            print("【Notify】Betting closed.")
            #play_sound(PIC_MP, volume=0.5)
            notified_2min = True


        if (target_time - timedelta(minutes=50)).time() < now_time < (target_time - timedelta(minutes=1)).time():
            odds_info = extract_odds_info(race_id)
            table = []
            #print(odds_info)
            # Filtering and displaying odds information
            for horse_no, odds in odds_info.items():
                horse_info = next((d["horse_info"] for d in data if d["race_id"] == race_id), {})
                win_rate = horse_info.get(horse_no, {}).get("win_rate", 0)
                rank_ranks = horse_info.get(horse_no, {}).get("rank_ranks", [])
                name_display = colored(to_romaji(odds['horse_name']), "red") if win_rate >= WIN_RATE_THRESHOLD and ODDS_MIN <= odds["odds_min"] <= ODDS_MAX else to_romaji(odds['horse_name'])
                table.append([
                    int(horse_no),
                    name_display,
                    colored(odds['win_odds'], "cyan"),
                    colored(odds['odds_min'], "green"),
                    odds['odds_max'],
                    round(win_rate, 2),
                    ",".join(rank_ranks)
                ])
            print(tabulate(table, headers=headers, tablefmt="grid", floatfmt=".1f"))
            countdown(WAIT_SEC)
        elif now_time > (target_time - timedelta(minutes=3)).time():
            print("Next race...")
            countdown(WAIT_SEC)
            break
        else:
            print(f"Waiting...")
            countdown(WAIT_SEC)

def find_next_race():
    now = datetime.now()
    future_races = [
        d for d in data
        if d["race_datetime"] > now #and d["horse_info"].get("__has_excellent__", False)
    ]

    print("\n=== Upcoming Races with Excellent Horses ===\n")
    for d in future_races:
        print(f"{d['site_name']} {d['race_num']}R | {d['rule']} | {d['race_datetime'].strftime('%H:%M')}")
        for horse_no, info in d["horse_info"].items():
            if horse_no.startswith("__"):
                continue  # 特殊キーはスキップ
            if info.get("win_rate", 0) >= WIN_RATE_THRESHOLD:
                past_ranks = info.get("rank_ranks", [])
                past_ranks_str = ",".join(past_ranks) if past_ranks else "N/A"
                print(f"  └ Excellent Horse: {horse_no} | PastRanks: {past_ranks_str}")

    print("\n=== Monitoring Next Race ===\n")
    while future_races:
        next_race = min(future_races, key=lambda x: x["race_datetime"])
        race_time = next_race["race_datetime"]
        detail = colored(f"{next_race['site_name']}{next_race['race_num']} | {next_race['rule']}", "yellow") + f" | {race_time.strftime('%H:%M')}"
        fetch_odds_periodically(next_race["race_id"], race_time, detail)

        now = datetime.now()
        future_races = [
            d for d in future_races
            if d["race_datetime"] > now and d["race_id"] != next_race["race_id"]
        ]

        if not future_races:
            print("No upcoming race with excellent horse.")
            break


#Main program
find_next_race()
