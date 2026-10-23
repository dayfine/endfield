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

## Correction (2026-10-22): AutoEssence is not available on Android

MaaEnd v2.34.0 limits **AutoEssence (基質刷取)** to Win32, Linux and PlayCover, not ADB.
TrialOfSwordmancy, StashBackpack, ItemTransfer and a few others are also PC-only (see
`docs/maaend_tasks_zh_tw.csv`, column 安卓(ADB)). PlayCover uses the ADB resource layer, so
forcing AutoEssence on for ADB in our generated interface may work. That's an experiment
(combat latency over ADB is unknown) and needs the user's OK, because it spends 理智.
AutoEssence's 目標選擇 mode picks the location and 預刻寫 for the ticked weapons by itself,
so if it works, our planner only has to choose the weapons.

All tasks and options with zh_tw labels and IDs: `docs/maaend_tasks_zh_tw.csv`. The Google
Sheet "終末地 日常任務選單" is the user-facing copy with a 想要? column.

## Phases

### Phase 0 — device bring-up (needs phone)
- `adb devices`, screencap, tap test.
- Record phone model, resolution, Android version, game version, and region.
- Capture reference screenshots in TC of: main screen, 行動手冊, 重度能量淤積點 entry,
  預刻寫 dialog, battle result, essence inventory and detail, daily rewards, mail.
- Done when: `endfield device check` prints the device and saves a screenshot.

**Device (found 2026-10-22):** Pixel 10 over USB, serial `5A060DLCR002CU`, Android 17,
arm64. Panel 1080x2424 (about 20:9). Game `com.gryphline.endfield.gp` 1.6.4 (Global client,
server Asia, 繁體中文). adb 36.0.0 bundled with scrcpy 3.3.3.

MaaEnd requires a 16:9 screen that scales to 1280x720, so the run forces
`adb shell wm size 1080x1920` and restarts the game. The game then lays itself out for
1920x1080, and screencap returns 1920x1080. Every run must call `wm size reset` on exit,
including on failure.

**Screens found (first capture, 2026-10-22):**
- Main menu (HUD top right) has 行動手冊, 通行證, 貴重品庫, 好友, 編隊 and more. 理智 shows
  as 135/360. The HUD has a direct 行動手冊 icon.
- 貴重品庫 → 武器 tab (981/2000). A 5-column grid, sorted by 品質 descending. The side panel
  shows name, type, rarity, the etched essence name, the 3 attributes with levels (e.g.
  智識提升·大 9/9), and who has it equipped. This screen is the weapon scan source.
- Weapon 詳情 → 基質 slot → 活性化 page shows the etched essence's 3 attributes with levels
  (+6/+6/+3), origin region, and a **卸下** button. **Essences can be removed**, which
  contradicts the earlier "can't remove" note. A strip along the bottom lists all
  essences, with a filter.
- 貴重品庫 → 武器基質 tab (411/2000, so the cap is 2000). The detail panel shows a
  **完美搭配** badge, origin, the 3 attributes with levels, which weapon it's equipped
  to, and 獲得方式.
- **基質願望清單** (native wishlist, up to 200 weapons, 9 set now). A gold essence that is a
  完美搭配 for any wishlisted weapon is **auto-locked by the game**. That replaces our
  own lock step (decision 7). Our job becomes choosing where to farm, and optionally
  keeping the wishlist in sync.
- 行動手冊 → 索引 → 能量淤積點: a list of 重度能量淤積點, 80 理智 each, with a region filter.
  Each row has a **基質總覽** (applicable weapons marked 裝備中/已持有/not owned, plus the
  8 附加 and 8 技能 attributes) and 查看. In-game data can cross-check `locations.json`.
- 查看 opens the map: 首通獎勵, 消耗理智領取獎勵 (理智 is spent when claiming after the
  battle), 前往傳送, 追蹤. Teleport works (free). Walking from the teleport to the node needs pathing (camera turns with movement), so use MaaEnd AutoEssence for it.
- 理智 potions (緊急理智加強劑) have expiry dates (36 left with 3 days, 13 with 10 days).
  The planner should use the expiring ones first.

### Phase 1 — infra and menu (done 2026-10-22)
- Python project (uv, Python 3.12), package in `src/endfield`.
- `endfield fetch` downloads the pinned release (`maaend.lock`: version, URL, sha256),
  mounts the dmg and copies `MaaEnd.app/Contents/MacOS` into gitignored `vendor/maaend`.
- `endfield device check | device size [force|reset] | screenshot | run <task>...`.
  `run` writes `runs/<timestamp>/` with the generated config, MaaPiCli output, maafw.log,
  and `failure.png` on failure.
- Done: `endfield run AndroidOpenGame` runs headless and completes.

**MaaPiCli notes** (headless works with `MaaPiCli -d`, which runs the saved config):
- The bundle ships `maafw/MaaPiCli` without the exec bit; `fetch` sets it.
- MaaPiCli loads the project (`interface.json`, resources, agents) and its config from
  the folder of its own libraries (`vendor/maaend/maafw`), not the cwd. `pi.prepare()`
  links `resource`, `resource_adb`, `tasks`, `locales`, `agent`, `data` into that folder,
  plus `maafw -> .`, because the agents run with that cwd and load `./maafw/libMaaFramework`.
- The bundled MaaPiCli can't parse the `hotkey` option type, so the generated
  `interface.json` drops `tasks/setting/Keymap.json` (PC keymaps). It also drops the
  Sentry `telemetry` block.
- The ADB device must be named `<serial>-<adb path>` (MaaToolkit's naming), and our adb
  must be on PATH. Otherwise MaaPiCli doesn't fill in screencap/input methods and
  controller creation fails.
- Exit code is always 0, even on a crash (its signal handler calls `exit(0)`). Success is
  `### All tasks have been completed ###` in the output. Runs time out after 1 hour.

### Phase 2 — daily routine

**Bring-up status (2026-10-22), `endfield run --preset daily --only <Task>`:**
- ✓ AndroidOpenGame, DailyRewards, VisitFriends, CreditShoppingN2, DeliveryJobs (uses the
  new quick hand-over), SellProduct (never switches goods), AutoStockpile (bought cheapest
  via 防溢出), EnvironmentMonitoring (all 4 photos), AutoEcoFarm (reached both maps).
- ✗ GiftOperator: fails at GiftOperatorSelectGiftOp (picking the operator).
- ~ DijiangRewards: passes, but only 快速收取 ran; clue exchange, clue gifting and
  再次種植 did not start. Check whether StageTaskSetting/FastCollect ends the task early.
- ? CreditShoppingN2 (2026-10-22, user report): credits were not spent. The task passes,
  but it may only buy 武庫配額 and 嵌晶玉 (Priority2/3 off, keep 300 in reserve), or it may
  not buy at all. The user is checking in game. Decide whether to fill Priority2/3.
- Not done yet: full end-to-end run, end-of-run summary, launchd watcher + notifications.

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

**Making MaaEnd match this phone (2026-10-22):**
- Force **720x1280**, not 1080x1920. Above 720p the game draws its HUD at 92% of MaaEnd's
  templates. Density makes no difference.
- In-game 設定 → 自訂邊界 must be **0** (it was 130). The margin pushes the HUD inward, out of
  MaaEnd's search areas. It reverted once after a restart, so check it again if matching
  breaks.
- `vendor/endfield_tc`: a generated layer that adds Traditional Chinese text (OpenCC s2t and
  s2twp) to MaaEnd OCR nodes that only have Simplified (290 nodes, including nested
  all_of/any_of). Terms that are worded differently, not just written differently (紙本紀錄
  vs 纸质记录), go in the hand-written layer.
- `resources/endfield`: hand-written fixes, loaded last. So far all are for IntelArchive.
  MaaEnd ships only PC templates for archive cards, and phone cards have a different shape.

### Phase 3b — 情報檔案庫 collection table (on demand)
Status: works. `endfield intel` → runs/<ts>/intel.csv → Google Sheet "終末地 情報檔案庫 收集表".
First full run: 361/535 pages marked collected. Known undercount: multi-page entries are
mostly unticked (MaaEnd records those by opening each card, the flaky step), and items
whose card would not open are skipped. Treat an unticked row as "maybe missing".

- `endfield intel` runs MaaEnd **IntelArchive** (ADB-capable, read-only). It scans
  情報檔案庫 and builds an "import payload" of unlocked entries, which it normally opens in
  Open Endfieldmap (opendfieldmap.org/intel).
- We capture that unlocked list (from the payload or the run log) and join it with MaaEnd's
  `data/IntelArchive/items.json`. That catalog has 501 items: 見聞輯錄 376, 中樞檔案 80,
  音像存檔 26, 情報採集 19, with zh_tw names, groups and related items. The region comes
  from the id (map01 = 四號谷地, map02 = 武陵).
- Output is one row per item: category, name, group, region, unlocked yes/no, and a map
  link. Where-to-find comes from Open Endfieldmap if its data can be fetched.
- Export to **Google Sheets** so the user can work from it. First version: the tool writes
  CSV and Claude pushes it to a sheet with the Sheets connector. Later: direct API
  (service account) if this needs to run unattended.
- First count (2026-10-22): 見聞輯錄 356/376, 中樞檔案 68/80, 音像存檔 25/26, so about 33
  are missing.

### Phase 4 — later
- Simple web page for the report; notifications; scheduled runs; more tasks
  (base/factory, 協議空間, events, 選劍演武 on ADB).

## Decisions (grilling session, 2026-10-22)

These override anything above that disagrees.

| # | Topic | Decision |
|---|---|---|
| 1 | Base | Build on MaaEnd + MaaFramework, our own Python on top. |
| 2 | MaaEnd source | Pinned **release bundle** (e.g. `MaaEnd-macos-aarch64-v2.34.0.dmg`), extracted to gitignored `vendor/maaend/` by a fetch script; version in `maaend.lock`. No submodule, no building agents. Use the bundle's own MaaFramework dylibs. |
| 3 | Running tasks | Hybrid: **MaaPiCli** (bundled) runs MaaEnd tasks from a generated `config/maa_pi_config.json`; the **Python binding** runs our own tasks (screenshots, weapon scan). Planner loop works per batch. Verify MaaPiCli runs non-interactively. |
| 4 | Targets | **Targets (updated 2026-10-22): every owned 6★ weapon, plus 5★ weapons that are equipped or above Lv 1.** Read by our weapon scan (貴重品庫 → 武器: rarity, level, 裝備中). |
| 5 | Done | A weapon is done when it has an essence matching all 3 attributes (any level). Planner: choose location + 3 基礎 + 1 lock covering the most unfinished weapons (≈1/24 per gold drop each); respect 谷地/武陵 刻寫券 budget. |
| 6 | Autonomy | Fully automatic: `daily` asks the planner, runs AutoEssence, logs drops (after-battle OCR), re-plans per batch. Full inventory rescan weekly. |
| 7 | Irreversible actions | **Locking is left to the game.** The in-game 基質願望清單 auto-locks 完美搭配 gold essences. We keep the wishlist in sync with all owned 5★/6★ weapons, and each save needs the user's OK. Never discard. Never etch: the report gives a "ready to etch" list. MaaEnd "discard unmatched" stays off. (Updated 2026-10-22 after the device capture.) |
| 8 | Triggering | Manual `endfield run daily` first, built for later `launchd`: one command, clear exit status, `runs/<date>/summary.json`, failure screenshots, lock file. USB ADB. |
| 9 | Game navigation | Reuse MaaEnd `SceneManager` (`SceneEnter*`, ~238 nodes). Add our own nodes only for the weapon list / weapon detail (likely 貴重品庫 weapon tab). CLI is plain subcommands; HTML report later. |
| 10 | Essence ↔ weapon | One essence per weapon. Done = matching essence **etched** (read from weapon detail) or a matching inventory essence **reserved** for it (allocated per combination). |
| 11 | License | AGPL-3.0 (repo is public). |
| 12 | Testing | pytest for planner/importers + screenshot-replay tests of our pipeline nodes (`tests/fixtures/`). Fixtures are 1280x720 PNGs with the UID blacked out (the HUD footer and the profile card). |
| 13 | Phase 0 | Capture list below; screenshots + navigation only, no 理智/ticket spending without approval. |

Defaults taken without asking: SQLite storage, Python 3.12 via uv, `config.yaml`.

### Phase 0 capture list

1. Device/client: `pm list packages | grep endfield` (→ ClientVersion), resolution/aspect,
   in-game language 繁體中文, graphics/FPS settings.
2. Weapon scan: 貴重品庫 weapon tab grid (top / scrolled / end, sort & filter), weapon
   detail with and without an etched essence, one 4★/5★/6★ each.
3. Essence inventory: grid, essence detail with levels, locked look, capacity display.
4. Farming: 行動手冊 → 重度能量淤積點 list → a location → 預刻寫 dialog (with 刻寫券
   count) → battle start → result screen with drops.
5. Daily TC check: main screen, mail, missions, pass, login popups.

### Still to confirm on device

- ~~MaaPiCli can run headless from a written config.~~ Yes (`-d`), see Phase 1 notes.
- Essence attribute level scale; storage capacity; how discard behaves.
- Etched essence attributes are readable on the weapon detail page.
- MaaEnd `RecoGrid`/`GridTracker` reusable for the weapon grid.

## References

- MaaEnd: https://github.com/MaaEnd/MaaEnd — see `assets/data/EssenceFilter/`,
  `agent/go-service/essencefilter/README.md`, `tools/essence_filter/README.md`,
  `assets/tasks/AutoEssence/`.
- MaaFramework: https://github.com/MaaXYZ/MaaFramework
- Mechanics (community guides, numbers may change by version): GamerSky 能量淤積點 guide,
  Bahamut 基質介紹 / 能量淤積刷取機率 threads, 17173 Endfield guides.
