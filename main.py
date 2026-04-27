import re,os,json,requests,time
from bs4 import BeautifulSoup
from datetime import datetime,timedelta
from charset_normalizer import detect

WIN_RATE_THRESHOLD = 0.1
ODDS_MIN, ODDS_MAX = 1.0, 5
SITE_IDS = [[30, "門別"], [44, "大井"], [47, "笠松"], [50, "園田"]]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}
TODAY = datetime.now()
YEAR, MONTH, DAY = TODAY.year, TODAY.month, TODAY.day
JSON_PATH = rf"C:\Users\yakim\OneDrive - 筑波大学\Unification\Keiba\datas\{MONTH:02d}{DAY:02d}.json"

print("\n","--- Program start ---")

def get_race_id(site_id: int, race_num: int) -> int:
    base_id = int(f"{YEAR:04d}{site_id:02d}{MONTH:02d}{DAY:02d}")
    return base_id * 100 + race_num


def fetch_html(url: str):
    res = requests.get(url, headers=HEADERS)
    res.encoding = res.apparent_encoding
    ret = BeautifulSoup(res.text, "html.parser")
    return ret

def extract_race_info(race_id: int):
    url = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"
    soup = fetch_html(url)
    #race start time
    time_tag = soup.select_one('div.RaceData01')
    m = re.search(r'(\d{1,2}):(\d{2})発走', time_tag.get_text())
    if not m:
        raise ValueError("No race")
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
        if wr >= 0.8:
            has_excellent = True
        horse_data[horse_no] = {
            "rank_ranks": ranks,
            "win_rate": wr
        }
    horse_data["__has_excellent__"] = has_excellent
    return race_time, horse_data

def extract_odds_info(race_id: int):
    url = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
    soup = fetch_html(url)
    odds_info = {}

    # Select rows from the odds table, similar to the first script
    odds_rows = soup.select("table.RaceOdds_HorseList_Table tr")[1:]

    for row in odds_rows:
        horse_no_tag = row.select_one("td.Waku")
        horse_name_tag = row.select_one("td.Horse_Name a")
        odds_tags = row.select("td.Odds span.Odds")
        if horse_no_tag and horse_name_tag and len(odds_tags) == 2:
            horse_no = horse_no_tag.text.strip()
            target_odds = odds_tags[1].text.strip()
            odds_range = target_odds.split(" - ")
            odds = float(odds_range[0])
            odds_info[horse_no] = {
                "horse_no": horse_no,
                "target_odds": odds
            }
    return odds_info


#Load JSON
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("Data loaded from JSON.","\n")
else:
    data = []
    for site_id, site_name in SITE_IDS:
        for race_num in range(1, 13):
            race_id = get_race_id(site_id, race_num)
            try:
                race_time, horse_info = extract_race_info(race_id)
                data.append({
                    "race_datetime": race_time.strftime("%H:%M"),
                    "race_id": race_id,
                    "site_name": site_name,
                    "race_num": race_num,
                    "horse_info": horse_info
                })
                print(f"Processed {site_name} {race_num}R at {race_time}")
            except Exception as e:
                print(f"[ERROR] {site_name} {race_num}R: {e}")

    data.sort(key=lambda x: x["race_datetime"])
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Saved data to {JSON_PATH}")

def fetch_odds_periodically(race_id: int, target_time: datetime):
    while True:
        now = datetime.now()
        now_time = now.time()
        if (target_time - timedelta(minutes=40)).time() < now_time < (target_time - timedelta(minutes=1)).time():
            print(f"Fetching odds for race ID {race_id}", "\n")
            odds_info = extract_odds_info(race_id)
            #print(odds_info)
            for horse_no, odds in odds_info.items():
                if ODDS_MIN <= odds["target_odds"] <= ODDS_MAX:  # Access target_odds here
                    print(f"{horse_no} - {odds['target_odds']} : {odds['target_odds']:.1f}")
            time.sleep(15)
        elif now_time > (target_time - timedelta(minutes=3)).time():
            print("Time passed, stopping fetch.")
            break
        else:
            print("Waiting for appropriate time...")
            time.sleep(10)

def find_next_race():
    now = datetime.now()
    future_races = [
        d for d in data
        if datetime.combine(now.date(), datetime.strptime(d["race_datetime"], "%H:%M").time()) > now
        and d["horse_info"].get("__has_excellent__", False)
    ]

    while future_races:
        # Fetch the next race with the earliest time
        next_race = min(future_races, key=lambda x: datetime.strptime(x["race_datetime"], "%H:%M"))

        print(f"Next race with excellent horse: {next_race['site_name']} {next_race['race_num']}R at {next_race['race_datetime']}")
        race_time = datetime.strptime(next_race["race_datetime"], "%H:%M")

        # Fetch odds for the race
        fetch_odds_periodically(next_race["race_id"], race_time)

        # Remove the processed race from the future_races list
        future_races = [
            d for d in data
            if datetime.combine(now.date(), datetime.strptime(d["race_datetime"], "%H:%M").time()) > now
            and d["horse_info"].get("__has_excellent__", False)
            and d["race_id"] != next_race["race_id"]
        ]

        # To avoid infinite loop, check if there are no more races with excellent horses
        if not future_races:
            print("No upcoming race with excellent horse.")
            break
#Main program
find_next_race()
