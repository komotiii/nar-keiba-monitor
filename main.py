import os
import json
import time
import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from charset_normalizer import detect
import concurrent.futures

# ========================== 設定 ==========================
win_rate = 0.6
odds_mi = 1.1
odds_ma = 1.4
race_min = 1
race_max = 12
json_path = r'C:\Users\yakim\OneDrive - 筑波大学\Unification\Keiba\race_results.json'
wait_margin_minutes = 10
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}
site_ids = [[44, "大井"], [46, "金沢"], [47, "笠松"], [50, "園田"]]

# ===================== レース取得関数 =====================
def get_odds_and_past_data(site_id, site_name, race_num, year, month, day):
    base_id = int(f"{year:04d}{site_id:02d}{month:02d}{day:02d}")
    race_id = base_id * 100 + race_num
    url_odds = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
    url_past = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"

    try:
        res_odds = requests.get(url_odds, headers=headers, timeout=10)
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

        res_past = requests.get(url_past, headers=headers, timeout=10)
        res_past.encoding = detect(res_past.content)['encoding']
        soup_past = BeautifulSoup(res_past.text, "html.parser")

        horse_rows_past = soup_past.select('tr.HorseList')

        for horse_block in horse_rows_past:
            horse_no_tag = horse_block.select_one('td.Waku')
            if not horse_no_tag:
                continue
            horse_no = horse_no_tag.text.strip()

            ranks = []
            for past_td in horse_block.select('td.Past'):
                if len(ranks) >= 5:
                    break
                data_item = past_td.select_one('div.Data_Item')
                if data_item:
                    num_span = data_item.select_one('div.Data01 span.Num')
                    if num_span:
                        ranks.append(num_span.text.strip())

            if horse_no in horse_info_by_number:
                horse_info_by_number[horse_no]["past_ranks"] = ranks

        picked_horses = []
        for horse in horse_info_by_number.values():
            odds_text = horse["fukusho_odds"]
            past_ranks = horse["past_ranks"]

            if odds_text in ["取消", "除外"]:
                continue
            try:
                odds_min = float(odds_text.split("-")[0].strip()) if "-" in odds_text else float(odds_text.strip())
            except ValueError:
                continue

            if odds_mi <= odds_min <= odds_ma:
                top3_count = sum(1 for r in past_ranks[:5] if r in ['1', '2', '3'])
                if top3_count / 5 >= win_rate:
                    picked_horses.append([
                        horse["horse_no"],
                        horse["name"],
                        odds_min,
                        past_ranks[:5]
                    ])

        return {
            "site_name": site_name,
            "site_num": site_id,
            "race_num": race_num,
            "race_time": f"{race_hour}:{race_minute:02d}",
            "race_datetime": race_datetime.isoformat(),
            "picked_horses": picked_horses
        }
    except Exception as e:
        print(f"[ERROR] {site_name} {race_num}R: {e}")
        return None

# ====================== JSONの読み書き ======================
def load_or_create_race_json():
    today = datetime.now()
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 今日以前のレースを削除
        data = [r for r in data if datetime.fromisoformat(r["race_datetime"]) > datetime.now()]
    else:
        data = []

    existing = {(r["site_num"], r["race_num"]) for r in data}

    # 取得対象のレースを探索・追加
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for site_id, site_name in site_ids:
            for race_num in range(race_min, race_max + 1):
                if (site_id, race_num) in existing:
                    continue
                futures.append(executor.submit(get_odds_and_past_data, site_id, site_name, race_num, today.year, today.month, today.day))

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                data.append(result)

    # 保存
    data.sort(key=lambda x: x["race_datetime"])
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return data

# ==================== 実行ループ ====================
def main():
    while True:
        data = load_or_create_race_json()
        future_races = [r for r in data if datetime.fromisoformat(r["race_datetime"]) > datetime.now()]

        if not future_races:
            print("本日のレースは全て終了しました。")
            break

        next_race = future_races[0]
        race_time = datetime.fromisoformat(next_race["race_datetime"])
        site = next_race["site_name"]
        num = next_race["race_num"]
        print(f"\n次のレース: {site} {num}R ({race_time.strftime('%H:%M')})")

        if next_race["picked_horses"]:
            print("注目馬:")
            for h in next_race["picked_horses"]:
                print(f" - {h[1]} (馬番: {h[0]}, オッズ: {h[2]}, 過去: {h[3]})")
        else:
            print("条件に合致する馬はいませんでした。")

        wait_sec = (race_time - timedelta(minutes=wait_margin_minutes) - datetime.now()).total_seconds()
        if wait_sec > 0:
            print(f"{wait_margin_minutes}分前まで {int(wait_sec)} 秒待機中...")
            time.sleep(wait_sec)
        else:
            print("すぐに次のレースに進みます。")

if __name__ == "__main__":
    main()
