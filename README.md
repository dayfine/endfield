# endfield

Automation for Arknights: Endfield (Traditional Chinese client) on Android over ADB:
daily routine, 重度能量淤積點 farming, and 武器基質 tracking.

See [docs/PLAN.md](docs/PLAN.md) for the research and plan.

## Usage

```sh
cp config.example.yaml config.yaml   # set adb path and device serial
uv run endfield fetch                # download the pinned MaaEnd bundle into vendor/
uv run endfield device check         # device info + screenshot
uv run endfield run AndroidOpenGame  # run MaaEnd tasks by name, headless
uv run pytest
```
