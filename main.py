import requests
from bs4 import BeautifulSoup
from datetime import datetime
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
}


site_id = 44  # サイトID（固定）


today = datetime.now()
year = today.year
month = today.month
day = today.day
base_id = int(f"{year:04d}{site_id:02d}{month:02d}{day:02d}")

url_top = "https://nar.netkeiba.com/top/race_list.html?kaisai_date=20250429#racelist_top_a"
url_odds = f"https://nar.netkeiba.com/odds/index.html?race_id={id}&rf=race_submenu"
url_past = f"https://nar.netkeiba.com/race/shutuba_past.html?race_id={id}&rf=shutuba_submenu"


# ========== Step 1: オッズページから 馬番・馬名・複勝オッズ 取得 ==========

res_odds = requests.get(url_odds, headers=headers)
res_odds.encoding = res_odds.apparent_encoding
soup_odds = BeautifulSoup(res_odds.text, "html.parser")

odds_rows = soup_odds.select("table.RaceOdds_HorseList_Table tr")[1:]

horse_info_by_number = {}

for row in odds_rows:
    horse_no_tag = row.select_one("td.Waku")  # 馬番（枠番ではない）
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
            "past_ranks": []  # あとで入れる
        }

# ========== Step 2: 過去レースページから 5レース分の順位取得 ==========

res_past = requests.get(url_past, headers=headers)
res_past.encoding = res_past.apparent_encoding
soup_past = BeautifulSoup(res_past.text, "html.parser")

horse_rows_past = soup_past.select('tr.HorseList')

for horse_block in horse_rows_past:
    horse_no_tag = horse_block.select_one('td.Waku')  # 馬番を取る
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

    # すでにオッズページで取ったデータに突き合わせる
    if horse_no in horse_info_by_number:
        horse_info_by_number[horse_no]["past_ranks"] = ranks

# ========== Step 3: 結果表示 ==========

print("\n[馬番, 馬名, 複勝オッズ, [過去レース順位(最大5件)]]：")
for horse in horse_info_by_number.values():
    print([horse["horse_no"], horse["name"], horse["fukusho_odds"], horse["past_ranks"]])

# ========== Step 3: Filter ==========
picked_horses = []

for horse in horse_info_by_number.values():
    horse_no = horse["horse_no"]
    horse_name = horse["name"]
    odds_text = horse["fukusho_odds"]
    past_ranks = horse["past_ranks"]

    # odds_text 例: "1.1 - 1.3"
    if "-" in odds_text:
        odds_min = float(odds_text.split("-")[0].strip())
    else:
        odds_min = float(odds_text.strip())

    # オッズ条件チェック (1.1～1.3)
    if 1.1 <= odds_min <= 1.3:
        # 過去10戦取得（5戦しか取ってなかったら5戦でもOK）
        past5 = past_ranks[:5]

        # 3着以内の回数をカウント
        top3_count = sum(1 for r in past5 if r in ['1', '2', '3'])

        if top3_count >= 3:
            picked_horses.append([horse_no, horse_name, odds_min, past5])

# 結果表示
print("\nピックアップされた馬：")
for horse in picked_horses:
    print(horse)
