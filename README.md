# endfield

Automation for Arknights: Endfield (Traditional Chinese client) on Android over ADB:
daily routine, 重度能量淤積點 farming, and 武器基質 tracking.

## Setup

```sh
cp config.example.yaml config.yaml   # set adb path, device serial, essence_farm weapons
uv run endfield fetch                # download the pinned MaaEnd bundle into vendor/
uv run endfield device check         # device info + screenshot
uv run pytest
```

Before any run: phone plugged in and unlocked. In game, 設定 → 自訂邊界 must be 0. Every
command forces the screen to 720x1280 and keeps it awake, then restores both afterwards
(`endfield device size reset` if a run was killed halfway).

## Running things by hand

Daily routine (about 22 min, spends no 理智; ends by closing the game):

```sh
uv run endfield run --preset daily --lock                  # whole preset, then screen off
uv run endfield run --preset daily --only DijiangRewards   # just some of its tasks
uv run endfield run --preset daily --dry-run               # check options, don't run
uv run endfield run AndroidOpenGame                        # any MaaEnd task by name
```

Essence (基質) farming, in this order:

```sh
uv run endfield weapons              # start on 貴重品庫 → 武器, sorted 品質 / 降序
uv run endfield essence scan         # export the 無瑕基質 inventory (read-only)
uv run endfield essence plan         # progress per weapon + numbered 預刻寫 steps
uv run endfield essence go 1         # teleport to step 1, set 預刻寫, stop before 開啟挑戰
uv run endfield essence farm 1 --rounds 3   # run off, wait, claim; 80 理智 per round, no medicine
```

`plan` reads the newest `weapons.json` and `EssenceInventory.json` under `runs/`, so
rerun `weapons` / `essence scan` when those change. Each `plan` saves itself to
`runs/essence_plan.json`, and the next plan only removes weapons from it (steps keep their
預刻寫 and order); delete that file to plan from scratch.

Other:

```sh
uv run endfield intel                # scan 情報檔案庫 → runs/<ts>/intel.csv
uv run endfield intel --no-run       # rebuild the CSV from the last run
uv run endfield screenshot
uv run endfield device size [show|force|reset]
```

## Where to look for state

- [docs/PLAN.md](docs/PLAN.md): the plan, what each phase has done, what's still open,
  and the decisions that override the rest (see "Decisions"). Start here.
- [docs/runlog/](docs/runlog/): one write-up per notable run (timeline, what went
  well/didn't, follow-ups), e.g. [2026-10-23-daily.md](docs/runlog/2026-10-23-daily.md).
- `runs/<timestamp>/` (gitignored, local only): raw output of each command, including
  `maafw.log`, `go-service.log`, screenshots, `failure.png`, and the `weapons.json`,
  `EssenceInventory.json`, `intel.csv` and `loot.png` outputs. Screenshots show the UID;
  don't share them.
- [config.yaml](config.example.yaml): what the daily preset does and which weapons are
  farmed. Option labels are in [docs/maaend_tasks_zh_tw.csv](docs/maaend_tasks_zh_tw.csv).
- `maaend.lock`: the pinned MaaEnd version.
