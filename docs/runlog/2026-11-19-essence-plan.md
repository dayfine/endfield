# Essence farming plan (2026-11-19)

From `endfield essence plan`, using weapon-first essence scan `20261119-230525`
(raw data: [2026-11-19-essence-scan.json](2026-11-19-essence-scan.json)).
Compared to the [2026-10-29 plan](2026-10-29-essence-plan.md), 6 of the 7 remaining
weapons now have a matching 無瑕基質 (equipped or unequipped in inventory), leaving
**顯赫聲名**, plus **驍勇** and **霧中微光** (newly added to `essence_farm`;
驍勇's matching 無瑕基質 is equipped on another weapon, so it still needs one).

## Where to farm

Run `endfield essence go N`, then `endfield essence farm N`.

| # | Location | 基礎 (pick 3) | 鎖 | Weapons | Odds per drop |
|---|----------|---------------|----|---------|---------------|
| 1 | 礦脈源區 | 主能力 / 敏捷 / 力量 | 物理傷害 | 顯赫聲名, 驍勇 | ~1/12 |
| 2 | 樞紐區 | 意志 / 主能力 / 力量 | 電磁傷害 | 霧中微光 | ~1/24 |

Dropped since 2026-10-29:
- Equipped with matching 無瑕基質: 遙望, 莫奈何, 探驪, 仰止, 點心時刻
- Unequipped matching 無瑕基質 in inventory: 嵌合正義, 典範

## Scan results (`essence_farm`)

| Weapon | Status | Notes |
|--------|--------|-------|
| 顯赫聲名 | `need_farming` | 未注入基質; no matching 無瑕基質 in 活性化 |
| 驍勇 | `need_farming` | 高純基質; matching 無瑕基質 in 活性化 is already equipped on another weapon |
| 霧中微光 | `need_farming` | 高純基質; no matching 無瑕基質 in 活性化 |
| 嵌合正義 | `in_inventory` | 未注入基質; unequipped matching 無瑕基質 found in 活性化 |
| 典範 | `in_inventory` | 未注入基質; unequipped matching 無瑕基質 found in 活性化 |
| 悼亡詩, 莫奈何, 扶搖, 悠久傳承, 白夜新星, 苦難的盡頭, 遙望, 聚合工業, 點心時刻, 仰止, 探驪, O.B.J.術識 | `equipped` | 無瑕基質 equipped (all 3 skills boosted) |
