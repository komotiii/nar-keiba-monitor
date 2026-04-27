import requests
from bs4 import BeautifulSoup
from datetime import datetime

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}

# 競馬場IDとその名前のマッピング
site_ids = [[44,"大井"],[46,"金沢"],[47,"笠松"],[50,"園田"]]  # 複数の競馬場ID
all_picked_horses = []

today = datetime.now()
year = today.year
month = today.month
day = today.day

for site_id, site_name in site_ids:
    base_id = int(f"{year:04d}{site_id:02d}{month:02d}{day:02d}")

    for race_num in range(1, 13):  # レース番号（例: 第8～12R）
        race_id = base_id * 100 + race_num

        url_odds = f"https://nar.netkeiba.com/odds/index.html?race_id={race_id}&rf=race_submenu"
        url_past = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={race_id}&rf=shutuba_submenu"

        # ========== Step 1: オッズページ ==========
        res_odds = requests.get(url_odds, headers=headers)
        res_odds.encoding = res_odds.apparent_encoding
        soup_odds = BeautifulSoup(res_odds.text, "html.parser")

        odds_rows = soup_odds.select("table.RaceOdds_HorseList_Table tr")[1:]
        horse_info_by_number = {}

        for row in odds_rows:
            horse_no_tag = row.select_one("td.Waku")
            horse_name_tag = row.select_one("td.Horse_Name a")
            odds_tags = row.select("td.Odds span.Odds")
            print(len(odds_tags))
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

        # ========== Step 2: 過去レースページ ==========
        res_past = requests.get(url_past, headers=headers)
        res_past.encoding = res_past.apparent_encoding
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
                data_item = past_td.select_one('div.Data_Item')
                if data_item:
                    num_span = data_item.select_one('div.Data01 span.Num')
                    if num_span:
                        rank = num_span.text.strip()
                        ranks.append(rank)

            if horse_no in horse_info_by_number:
                horse_info_by_number[horse_no]["past_ranks"] = ranks


        # ========== Step 3: フィルタ ==========
        picked_horses = []

        for horse in horse_info_by_number.values():
            horse_no = horse["horse_no"]
            horse_name = horse["name"]
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

            if 1.0 <= odds_min <= 1.3:
                past5 = past_ranks[:5]
                top3_count = sum(1 for r in past5 if r in ['1', '2', '3'])
                if top3_count >= 4:
                    picked_horses.append([horse_no, horse_name, odds_min, past5])

        # ↓ここで場所とレース番号を表示
        print(f"\n--- {site_name} 競馬場 - レース番号 {race_num} ---")
        for horse in picked_horses:
            print(horse)

        # まとめ用にも保存（必要なら）
        all_picked_horses.append({
            "race_id": race_id,
            "picked_horses": picked_horses
        })
