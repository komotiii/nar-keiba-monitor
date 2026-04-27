import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from charset_normalizer import detect
import concurrent.futures
import re
import json

win_rate = 0.6
odds_mi = 1.1
odds_ma = 1.4
race_min = 1
race_max = 12
nowtime_delay_min = 0;
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}
#site_ids = [[50, "園田"]]
site_ids = [[44, "大井"], [46, "金沢"], [47, "笠松"], [50, "園田"]]

def get_odds_and_past_data(site_id, site_name, race_num, year, month, day):
    base_id = int(f"{year:04d}{site_id:02d}{month:02d}{day:02d}")
    race_id = base_id * 100 + race_num
    url_odds = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
    url_past = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"

    res_odds = requests.get(url_odds, headers=headers)
    res_odds.encoding = detect(res_odds.content)['encoding']
    soup_odds = BeautifulSoup(res_odds.text, "html.parser")

    race_data_div = soup_odds.select_one('div.RaceData01')
    if not race_data_div:
        return None

    m = re.search(r'(\d{1,2}):(\d{2})発走', race_data_div.get_text())
    if not m:
        return None
    race_hour, race_minute = int(m.group(1)), int(m.group(2))
    race_datetime = datetime(year, month, day, race_hour, race_minute)

    odds_rows = soup_odds.select("table.RaceOdds_HorseList_Table tr")[1:]
    horse_info_by_number = {}

    for row in odds_rows:
        horse_no_tag = row.select_one("td.Waku")
        horse_name_tag = row.select_one("td.Horse_Name a")
        odds_tags = row.select("td.Odds span.Odds")

        if horse_no_tag and horse_name_tag and len(odds_tags) == 2:
            horse_no = horse_no_tag.text.strip()
            horse_name = horse_name_tag.text.strip()
            fukusho_odds = odds_tags[1].text.strip()

            horse_info_by_number[horse_no] = {
                "horse_no": horse_no,
                "name": horse_name,
                "fukusho_odds": fukusho_odds,
                "past_ranks": []
            }

    res_past = requests.get(url_past, headers=headers)
    res_past.encoding = detect(res_past.content)['encoding']
    soup_past = BeautifulSoup(res_past.text, "html.parser")

    horse_rows_past = soup_past.select('tr.HorseList')

    for horse_block in horse_rows_past:
        horse_no_tag = horse_block.select_one('td.Waku')
        if not horse_no_tag:
            continue
        horse_no = horse_no_tag.text.strip()

        ranks = []
        past_tds = horse_block.select('td.Past')
        for past_td in past_tds:
            if len(ranks) >= 5:
                break
            data_item = past_td.select_one('div.Data_Item')
            if data_item:
                num_span = data_item.select_one('div.Data01 span.Num')
                if num_span:
                    rank = num_span.text.strip()
                    ranks.append(rank)

        if horse_no in horse_info_by_number:
            horse_info_by_number[horse_no]["past_ranks"] = ranks

    picked_horses = []

    for horse in horse_info_by_number.values():
        odds_text = horse["fukusho_odds"]
        past_ranks = horse["past_ranks"]

        if odds_text in ["取消", "除外"]:
            continue
        try:
            if "-" in odds_text:
                odds_min = float(odds_text.split("-")[0].strip())
            else:
                odds_min = float(odds_text.strip())
        except ValueError:
            continue

        if odds_mi <= odds_min <= odds_ma:
            past5 = past_ranks[:5]
            top3_count = sum(1 for r in past5 if r in ['1', '2', '3'])
            if top3_count/5 >= win_rate:
                picked_horses.append([
                    horse["horse_no"],
                    horse["name"],
                    odds_min,
                    past5
                ])

    return site_name, race_num, f"{race_hour}:{race_minute:02d}", race_datetime, picked_horses

# ======================== メイン処理 ========================
today = datetime.now()
year, month, day = today.year, today.month, today.day
results = []

total_tasks = len(site_ids) * (race_max - race_min + 1)
completed = 0

with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = []
    for site_id, site_name in site_ids:
        for race_num in range(race_min, race_max + 1):
            futures.append(executor.submit(get_odds_and_past_data, site_id, site_name, race_num, year, month, day))

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        completed += 1

        print(f"進捗：{completed}/{total_tasks} 件完了 ({completed/total_tasks*100:.1f}%)")

        if result is None:
            continue
        site_name, race_num, race_time, race_datetime, picked_horses = result
        if race_datetime < datetime.now() + timedelta(minutes=nowtime_delay_min):
            continue
        results.append((race_datetime, site_name, race_num, race_time, picked_horses))

# 発走時刻でソート
results.sort(key=lambda x: x[0])

for race_datetime, site_name, race_num, race_time, picked_horses in results:
    print(f"\n--- {site_name}- {race_num}R -{race_time} ---")
    for horse in picked_horses:
        print(horse)

# JSONに保存する部分
output_data = []

for race_datetime, site_name, race_num, race_time, picked_horses in results:
    # site_name に対応する site_num を取得
    site_num = next(site_id for site_id, name in site_ids if name == site_name)

    # レース情報をJSONデータに追加
    race_data = {
        "site_name": site_name,
        "site_num": site_num,  # site_num を追加
        "race_num": race_num,
        "race_time": race_time
    }
    output_data.append(race_data)

# JSONファイルとして保存
with open(r'C:\Users\yakim\OneDrive - 筑波大学\Unification\Keiba\race_results.json', 'w', encoding='utf-8') as f:
    json.dump(output_data, f, ensure_ascii=False, indent=4)

print("\nレース結果が 'race_results.json' に保存されました。")
