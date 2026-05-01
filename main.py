import re, os, json, requests, time, sys
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from tabulate import tabulate
from termcolor import colored
import pygame
from charset_normalizer import detect

# =========================================%
# 設定ファイルの読み込み
# =========================================%
CONFIG_FILE = "config.json"
try:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"[エラー] 設定ファイル '{CONFIG_FILE}' が見つかりません。")
    sys.exit(1)

# 変数のマッピング
WIN_RATE_THRESHOLD = config["thresholds"]["win_rate"]
ODDS_MIN = config["thresholds"]["odds_min"]
ODDS_MAX = config["thresholds"]["odds_max"]
SITE_IDS = config["site_ids"]
WAIT_SEC = config["wait_sec"]
HEADERS = config["headers"]

# パスと日付の設定
TODAY = datetime.now()
YEAR, MONTH, DAY = TODAY.year, TODAY.month, TODAY.day

DATA_DIR = config["paths"]["data_dir"]
# data_dirとファイル名(MMDD.json)を結合
JSON_PATH = os.path.join(DATA_DIR, f"{MONTH:02d}{DAY:02d}.json")

PIC_MP = config["paths"]["audio_pic"]
FTN_MP = config["paths"]["audio_ftn"]
# ==========================================

# ヘッダーを日本語化して視認性を向上
headers = ["馬番", "馬名", "単勝", "複勝(下限)", "複勝(上限)", "複勝率(直近)", "過去着順"]

def clear_console():
    """コンソール画面をクリアしてダッシュボードのように見せる"""
    os.system('cls' if os.name == 'nt' else 'clear')

print("\n=== Program start ===\n")

def play_sound(path, volume=1.0):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(volume)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"音声の再生に失敗しました: {e}")

def countdown(sec):
    print("\n")
    for remaining in range(sec, 0, -1):
        print(f"\r次の更新まで {remaining:2d} 秒お待ちください...   ", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 40 + "\r", end="", flush=True)

def get_race_id(site_id: int, race_num: int) -> int:
    base_id = int(f"{YEAR:04d}{site_id:02d}{MONTH:02d}{DAY:02d}")
    return base_id * 100 + race_num

def fetch_html(url: str):
    res = requests.get(url, headers=HEADERS, timeout=15)
    html_text = res.content.decode("euc-jp", errors="ignore")
    return BeautifulSoup(html_text, "html.parser")

def extract_race_info(race_id: int):
    url = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"
    soup = fetch_html(url)

    time_tag = soup.select_one('div.RaceData01')
    if not time_tag:
        raise ValueError("No race data block")

    race_text = time_tag.get_text(" ", strip=True)
    m = re.search(r'(\d{1,2})[:：](\d{2})\s*発走', race_text)
    if not m:
        m = re.search(r'(\d{1,2})[:：](\d{2})', race_text)
    if not m:
        raise ValueError("No race start time")

    rule_match = re.search(r'(ダ|芝)\s*[0-9,]{3,5}\s*m', race_text)
    rule = rule_match.group(0).replace(" ", "") if rule_match else "N/A"

    race_time = datetime(YEAR, MONTH, DAY, int(m.group(1)), int(m.group(2)))
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
                win_odds = odds_min = odds_max = None
            else:
                try:
                    win_odds = float(odds_text)
                    place_range = place_text.split(" - ")
                    odds_min = float(place_range[0])
                    odds_max = float(place_range[1])
                except Exception:
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
                race_time, horse_info, rule = extract_race_info(race_id)
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
                pass

    data.sort(key=lambda x: x["race_datetime"])

    data_to_save = []
    for d in data:
        d_copy = d.copy()
        if isinstance(d_copy["race_datetime"], datetime):
            d_copy["race_datetime"] = d_copy["race_datetime"].isoformat()
        data_to_save.append(d_copy)

    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    print(f"Saved data to {JSON_PATH}")
    return data

# Load JSON
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("Data loaded from JSON.\n")
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
        time_to_start = (target_time - now).total_seconds()

        if not notified_5min and 0 < time_to_start <= 300:
            print("【Notify】Betting closes in 3 minutes.")
            play_sound(FTN_MP, volume=1)
            notified_5min = True
        if not notified_2min and 0 < time_to_start <= 120:
            print("【Notify】Betting closed.")
            play_sound(PIC_MP, volume=0.5)
            notified_2min = True

        if (target_time - timedelta(minutes=50)).time() < now_time < (target_time - timedelta(minutes=1)).time():
            odds_info = extract_odds_info(race_id)
            table = []

            for horse_no, odds in odds_info.items():
                horse_info = next((d["horse_info"] for d in data if d["race_id"] == race_id), {})
                win_rate = horse_info.get(horse_no, {}).get("win_rate", 0)
                rank_ranks = horse_info.get(horse_no, {}).get("rank_ranks", [])

                is_target = win_rate >= WIN_RATE_THRESHOLD and (odds["odds_min"] is not None and ODDS_MIN <= odds["odds_min"] <= ODDS_MAX)

                horse_name = odds['horse_name']
                name_display = colored(horse_name, "red", attrs=["bold"]) if is_target else horse_name

                win_odds_str = colored(f"{odds['win_odds']:.1f}", "cyan") if odds['win_odds'] else "-"
                odds_min_str = colored(f"{odds['odds_min']:.1f}", "green") if odds['odds_min'] else "-"
                odds_max_str = f"{odds['odds_max']:.1f}" if odds['odds_max'] else "-"

                table.append([
                    int(horse_no),
                    name_display,
                    win_odds_str,
                    odds_min_str,
                    odds_max_str,
                    f"{win_rate:.2f}",
                    ",".join(rank_ranks)
                ])

            clear_console()
            print(f"現在時刻: {now.strftime('%H:%M:%S')} | 発走: {target_time.strftime('%H:%M')}")
            print(detail)
            print(tabulate(table, headers=headers, tablefmt="grid"))
            countdown(WAIT_SEC)

        elif now_time > (target_time - timedelta(minutes=3)).time():
            print("\n次のレースへ移行します...")
            countdown(5)
            break
        else:
            clear_console()
            print(f"待機中... 発走時刻: {target_time.strftime('%H:%M')} (現在: {now.strftime('%H:%M:%S')})")
            countdown(WAIT_SEC)

def find_next_race():
    now = datetime.now()
    future_races = [
        d for d in data
        if d["race_datetime"] > now
    ]

    print("\n=== Upcoming Races with Excellent Horses ===\n")
    for d in future_races:
        print(f"{d['site_name']} {d['race_num']}R | {d['rule']} | {d['race_datetime'].strftime('%H:%M')}")
        for horse_no, info in d["horse_info"].items():
            if horse_no.startswith("__"):
                continue
            if info.get("win_rate", 0) >= WIN_RATE_THRESHOLD:
                past_ranks = info.get("rank_ranks", [])
                past_ranks_str = ",".join(past_ranks) if past_ranks else "N/A"
                print(f"  └ 注目馬: {horse_no}番 | 過去着順: {past_ranks_str}")

    time.sleep(3)

    while future_races:
        next_race = min(future_races, key=lambda x: x["race_datetime"])
        race_time = next_race["race_datetime"]
        detail = colored(f"■ {next_race['site_name']} {next_race['race_num']}R | {next_race['rule']}", "yellow", attrs=["bold"])

        fetch_odds_periodically(next_race["race_id"], race_time, detail)

        now = datetime.now()
        future_races = [
            d for d in future_races
            if d["race_datetime"] > now and d["race_id"] != next_race["race_id"]
        ]

        if not future_races:
            print("本日の監視対象レースは終了しました。")
            break

if __name__ == "__main__":
    find_next_race()
