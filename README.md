# nar-keiba-monitor

地方競馬 (NAR) の出走表・過去成績・オッズを取得し、
条件に合う馬を監視表示する Python スクリプトです。

データソース

- https://nar.netkeiba.com

## What It Does

- レースIDを自動生成して対象レースを巡回
- 出走表ページから発走時刻・コース情報・過去成績を取得
- オッズページから単勝・複勝オッズを取得
- 指定条件に合う馬をテーブル表示
- 次レースまでの待機・発走前監視ループを実行

## Main Script

- `main.py`

このリポジトリは、`main.py` を中心に完結する構成です。

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
python main.py
```

## Configuration (in script)

- `WIN_RATE_THRESHOLD`: 過去成績の判定閾値
- `ODDS_MIN`, `ODDS_MAX`: 複勝オッズの表示条件
- `SITE_IDS`: 監視する競馬場
- `WAIT_SEC`: オッズ再取得の間隔

## Notes

- サイト構造変更によりスクレイピングが失敗する場合があります。
- 音声通知パスはローカル環境向け設定です。
- `datas/` はキャッシュ用途のため Git 管理対象外にしています。
