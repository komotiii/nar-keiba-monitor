import re,os,json,requests
from bs4 import BeautifulSoup
from datetime import datetime
from charset_normalizer import detect

print("\n","--- Program start ---","\n")

win_rate = 0.6
odds_mi, odds_ma = 1.1, 1.4
# site_ids = [[44, "大井"], [46, "金沢"], [47, "笠松"], [50, "園田"]] 29火曜日
site_ids = [[30, "門別"], [44, "大井"], [47, "笠松"], [50, "園田"] ]#30火曜日
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"}
today = datetime.now()
year, month, day = today.year, today.month, today.day

def get_base_link(site_num):
    base_id = int(f"{year:04d}{site_num:02d}{month:02d}{day:02d}")
    return base_id


def fetch_html(url: str) -> BeautifulSoup:
    res = requests.get(url, headers=HEADERS)
    res.encoding = detect(res.content)['encoding']
    return BeautifulSoup(res.text, "html.parser")

def get_ranks_data(race_id):
    url_rank = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"#print(url_rank)
    res_rank = requests.get(url_rank, headers=headers)
    res_rank.encoding = detect(res_rank.content)['encoding']
    soup = BeautifulSoup(res_rank.text, "html.parser")
    #race start time
    race_data_div = soup.select_one('div.RaceData01')
    m = re.search(r'(\d{1,2}):(\d{2})発走', race_data_div.get_text())
    if m is None:
        raise ValueError(f"No race")
    race_hour, race_minute = int(m.group(1)), int(m.group(2))
    race_datetime = datetime(year, month, day, race_hour, race_minute)
    # get horse ranks
    horse_info = {}
    has_excellent_horse = False
    tr_rows = soup.select('tr.HorseList')
    for tr in tr_rows:
        horse_no_tag = tr.select_one('td.Waku')
        horse_no = horse_no_tag.text.strip()
        ranks = []
        rank_tds = tr.select('td.Past')
        for td in rank_tds:
            data_item = td.select_one('div.Data_Item')
            span = data_item.select_one('div.Data01 span.Num')
            if span:
                ranks.append(span.text.strip())
        top3 = sum(1 for r in ranks if r in ['1', '2', '3'])
        wr = top3 / max(5,len(ranks)) if ranks else 0
        if wr >= 0.8:
            has_excellent_horse = True
        horse_info[horse_no] = {
            'rank_ranks': ranks,
            'win_rate': wr
        }
    horse_info["__has_excellent__"] = has_excellent_horse
    return race_datetime, horse_info

def get_odds_data(race_id):
    url_odds = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
    res_odds = requests.get(url_odds, headers=headers)
    res_odds.encoding = detect(res_odds.content)['encoding']
    soup_odds = BeautifulSoup(res_odds.text, "html.parser")
    odds_rows = soup_odds.select("table.RaceOdds_HorseList_Table tr")[1:]

    odds_info = {}
    for row in odds_rows:
        horse_no_tag = row.select_one("td.Waku")
        horse_name_tag = row.select_one("td.Horse_Name a")
        odds_tags = row.select("td.Odds span.Odds")

        if horse_no_tag and horse_name_tag and len(odds_tags) == 2:
            horse_no = horse_no_tag.text.strip()
            horse_name = horse_name_tag.text.strip()
            targe_odds = odds_tags[1].text.strip()
            odds_info[horse_no] = {
                "name": horse_name,
                "targe_odds": float(targe_odds)
            }
    return odds_info


# main program
json_file_path = rf"C:\Users\yakim\OneDrive - 筑波大学\Unification\Keiba\datas\{month:02d}{day:02d}.json"

#Load JSON
if os.path.exists(json_file_path):
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Data Loaded.")
else:
    data = []
    for site_id, site_name in site_ids:
        for race_num in range(1, 13):
            race_id = get_base_link(site_id) * 100 + race_num
            try:
                race_datetime, horse_info = get_ranks_data(race_id)
                data.append({
                    "race_datetime": race_datetime.strftime("%H:%M"),
                    "race_id": race_id,
                    "site_name": site_name,
                    "race_num": race_num,
                    "horse_info": horse_info
                })
                print(f"Processed {site_name} {race_num}R at {race_datetime}")
            except Exception as e:
                print(f"[ERROR] {site_name} {race_num}R: {e}")
    #Sort by race_time
    data.sort(key=lambda x: x["race_datetime"])
    #Save to JSON file
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"Saved data to {json_file_path}.")


now = datetime.now()


# future_races 抽出も修正
future_races = [
    d for d in data
    if datetime.combine(now.date(), datetime.strptime(d["race_datetime"], "%H:%M").time()) > now
    and d["horse_info"].get("__has_excellent__", False)
]


if future_races:
    closest_race = min(future_races, key=lambda x: datetime.strptime(x["race_datetime"]))
    print(f"Next race with excellent horse: {closest_race['site_name']} {closest_race['race_num']}R at {closest_race['race_datetime']}")

    odds_info = get_odds_data(closest_race["race_id"])
    print(f"Retrieved odds for race ID {closest_race['race_id']}")

    # フィルタして表示（例えば、指定odds範囲内）
    for horse_no, info in odds_info.items():
        odds_val = info["targe_odds"]
        if odds_mi <= odds_val <= odds_ma:
            print(f"★ {horse_no} - {info['name']} : {odds_val}")
else:
    print("No upcoming race with excellent horse.")
