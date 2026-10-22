# Arknights: Endfield automation plan

Status: research done, no device connected yet. Date: 2026-10-22.

## Goals

1. **Daily routine** — daily/weekly rewards, mail, pass, shop, and spending 理智 on
   **重度能量淤積點** (needs real combat: walk in, fight, claim).
2. **武器基質 tracking** — know which essences I own, which weapons they fit, and
   where/how to farm the missing ones. This is a data join (weapons × locations × inventory).
3. **Infra** — Android control over USB ADB, a task menu/CLI, screenshots and logs, so
   later tasks are cheap to add.

Constraint: game client language is **Traditional Chinese (TC)**, on an Android phone.

## Key finding: MaaEnd already exists

[MaaEnd](https://github.com/MaaEnd/MaaEnd) (AGPL-3.0, very active — last commit 2026-10-22)
is a MaaFramework-based Endfield bot that already:

- supports an **ADB controller** (`assets/resource_adb/` overrides the PC pipelines) and
  ships a **zh_tw** UI locale; its essence OCR normalizes CN/TC/EN/JP/KR;
- has `AutoEssence` (repeatedly runs 重度能量淤積點 with 預刻寫 and claims rewards),
  `AutoFight`, `DailyRewards`, `CreditShopping`, `DeliveryJobs`, etc.;
- has `EssenceFilter`: scans the essence inventory grid, OCRs the 3 skills + levels,
  matches against all weapons, can lock/discard, and can **export `EssenceInventory.json`**;
- ships the game data we need for the join (`assets/data/EssenceFilter/`, generated from
  game tables by their `zmdmap` tool, data version 2026-10-08):
  - `weapons_output.json` — 84 weapons (47×6★), each with its 3 essence skills in 14 languages;
  - `skill_pools.json` — the 3 slots: 基礎屬性 (5), 附加屬性 (12), 技能屬性 (14);
  - `locations.json` — 13 重度能量淤積點, each with its 8 附加 + 8 技能 attribute pool.

Writing all of this from scratch would mean redoing hundreds of pipeline nodes,
templates and a combat module. **Recommendation: build on MaaFramework and reuse MaaEnd,
and spend our own effort on what it doesn't do: the tracker/planner and our own menu.**

### MaaEnd tasks available on ADB

- Daily chores: 日常獎勵, 百科紅點, 簡制手冊, 拜訪好友, 帝江號/基建, 資源回收站, Baker
- Spending 理智: 基質刷取 (AutoEssence), 協議空間, 環境監測
- 基質: 基質篩選, inventory export, 分解武器基質
- Economy: 信用點購物, 據點交易, 自動倒賣, 送貨任務, 委託搶單
- Field: 自動採集, 生態農場, 批量探測器
- Progression: 武器升級, 裝備組裝, 生產製造, 幹員升級, 贈送幹員禮物, 切換編隊
- Info: 抽數計算, 情報檔案庫, 滑索座標導入
- App: open / close game

PC/Linux only (not ADB): 選劍演武, 影拓豐碑, 解拼圖, 即時開荒輔助, 浮空回收,
存放背包, 庫存轉移, 藍圖導入, 自動切換帳號, 批量加/刪好友.

## Game mechanics we rely on (to be confirmed on device)

- An essence (基質) has 3 attributes: **基礎屬性** (主能力/力量/意志/敏捷/智識),
  **附加屬性** (攻擊, 生命, 物理, 灼熱, 電磁, 寒冷, 自然, 暴擊率, 源石技藝強度,
  終結技蓄能, 法術, 治療), **技能屬性** (強攻, 壓制, 追襲, 粉碎, 巧技, 迸發, 流轉, 效益,
  昂揚, 附術, 醫療, 切骨, 殘暴, 夜幕).
- Every weapon wants one specific value in each slot (some 4★ have only 2). An essence
  only helps if its attributes match.
- 重度能量淤積點: 80 理智 per run → about 3 gold + 2 purple essences. Each location has a
  fixed pool of 8 附加 + 8 技能, so a weapon can only be finished at locations whose pools
  contain both of its 附加 and 技能.
- **預刻寫** (uses 谷地/武陵刻寫券, bought weekly in 物資調度): before the run, pick 3
  基礎屬性 and lock either 1 附加 or 1 技能. Without it a full match is about 1/320;
  every guide says always use it.
- No way to remove an essence from a weapon, so tracking must be careful.

Sample join from MaaEnd's data (scratch run): all 47 6★ weapons have at least one
location. E.g. 典範 (主能力/攻擊/壓制) → 樞紐區, 源石研究園, 應龍關, 祀的畫.

## Architecture

```
┌──────────────┐  CLI menu / later web UI
│  endfield    │  (our repo, Python)
│  ├ cli       │  run task presets, show status
│  ├ device    │  adb connect, screencap, health checks
│  ├ runner    │  MaaFramework Python binding (`maafw` on PyPI)
│  ├ tracker   │  essence DB + weapon/location join + farming planner
│  └ data      │  synced game data (weapons, pools, locations)
└──────┬───────┘
       │ loads resource bundles in layers
┌──────▼───────────────────────────────────────┐
│ MaaEnd resources (submodule, pinned commit)   │
│   resource → resource_adb (+ our overrides)   │
│ MaaEnd agents (go-service, cpp-algo) prebuilt │
└──────┬───────────────────────────────────────┘
       │ ADB (USB, or adb over TCP)
   Android phone (TC client)
```

- **Control**: MaaFramework's AdbController (screencap/input methods picked automatically;
  MaaFramework works at 720p internally, so phone resolution only needs a 16:9-ish aspect).
- **Tasks**: run MaaEnd task entry points by name, with our own option presets. Anything
  MaaEnd lacks or gets wrong for TC goes into our own resource layer loaded after theirs
  (MaaFramework merges same-name nodes), so we don't fork.
- **Tracker** (our own code, simple and testable without a phone):
  - input 1: MaaEnd's `EssenceInventory.json` export (or our own scan later);
  - input 2: `weapons_output.json`, `locations.json`, `skill_pools.json`;
  - input 3: my list of target weapons / operators (YAML);
  - store: SQLite (`essences`, `weapons`, `locations`, `targets`, `runs`);
  - outputs: per target weapon, the best owned essence and its match level; missing
    targets → candidate locations, the 預刻寫 that covers the most targets at once, and
    expected runs/理智; a history of farming runs (drops per run).
- **Licensing**: MaaEnd is AGPL-3.0. Using it as a submodule for personal use is fine;
  if we ever publish our repo with copied MaaEnd code or pipelines, our repo is AGPL too.
  Keep a clear line: submodule + our own overrides + our own Python.

## Phases

### Phase 0 — device bring-up (needs phone)
- `adb devices`, screencap, tap test.
- Record phone model, resolution, Android version, game version, and region.
- Capture reference screenshots in TC of: main screen, 行動手冊, 重度能量淤積點 entry,
  預刻寫 dialog, battle result, essence inventory and detail, daily rewards, mail.
- Done when: `endfield device check` prints the device and saves a screenshot.

### Phase 1 — infra and menu
- Python project (uv), `maafw` dependency, MaaEnd as a pinned git submodule, script that
  downloads the matching prebuilt agents from MaaEnd's releases.
- `endfield` CLI: `device check`, `screenshot`, `run <task|preset>`, `list`, with logs
  and a screenshot on failure in `runs/<timestamp>/`.
- Config file: device serial, presets (which tasks, options), target weapons.
- Done when: a no-op MaaEnd task (open game / go to main screen) runs from our CLI.

### Phase 2 — daily routine
- Preset `daily`: start game → DailyRewards → mail/pass → shops → AutoEssence with N
  runs (spend 理智) → EssenceFilter after battle (lock matches, never auto-discard at first).
- Check every step on the TC client; add TC-specific overrides where OCR or templates fail.
- Done when: `endfield run daily` finishes 3 days in a row with no manual help.

### Phase 3 — 基質 tracker
- Sync data from MaaEnd's `assets/data/EssenceFilter` (record the data version).
- Import `EssenceInventory.json` into SQLite; diff against the last import.
- `endfield essence report`: target weapons → best owned essence, gaps, recommended
  location + 預刻寫, rough runs needed. Show which existing locks are now useless.
- Feed the planner's choice (location + 預刻寫) back into the AutoEssence options, so the
  daily run farms what the tracker says is most needed.
- Done when: the report matches what I see in game for a handful of weapons.

### Phase 4 — later
- Simple web page for the report; notifications; scheduled runs; more tasks
  (base/factory, 協議空間, events, 選劍演武 on ADB).

## Open questions

1. **OK to build on MaaEnd** (submodule + overrides), or a from-scratch implementation
   for learning/ownership? The plan assumes reuse.
2. **Server/region**: global TC client, or a TW/HK-specific one? Affects login flow.
3. **Tracking scope**: is "what I own vs. what my target weapons need, and where to farm"
   the right output? Should it also cover weapons not owned yet?
4. Should automation ever **discard** essences, or only lock/report?

## References

- MaaEnd: https://github.com/MaaEnd/MaaEnd — see `assets/data/EssenceFilter/`,
  `agent/go-service/essencefilter/README.md`, `tools/essence_filter/README.md`,
  `assets/tasks/AutoEssence/`.
- MaaFramework: https://github.com/MaaXYZ/MaaFramework
- Mechanics (community guides, numbers may change by version): GamerSky 能量淤積點 guide,
  Bahamut 基質介紹 / 能量淤積刷取機率 threads, 17173 Endfield guides.
