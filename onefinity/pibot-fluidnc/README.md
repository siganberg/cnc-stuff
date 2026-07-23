# PiBot FluidNC — TMC5160T Pro Conversion

CNC router controller setup: **PiBot V4.96 Pro** (firmware reports `PiBotV49P`) running **FluidNC v4.0.3**, converted from dumb stepsticks to **4× BTT TMC5160T Pro** SPI drivers with **sensorless (StallGuard) homing**.

- Board IP: `10.0.2.28` (WiFi STA), Telnet :23, HTTP :80, WebUI at `http://10.0.2.28`
- Machine: XYZ router, **ganged Y** (Y2 = Y `motor1`, physically in the Motor 4 slot)
- Motors: NEMA 23, 1.8°, 1.26 Nm, **2.8 A/phase (peak)**, 2.5 V rated, 24 V supply
- Mechanics: 400 steps/mm @ 16 microsteps (8 mm-lead screws)

## Files

| File | What |
|---|---|
| `config-tmc5160.yaml` | **The live config** (golden copy). Push this to the board. |
| `original-config-pre-tmc5160.yaml` | Pre-conversion config (stepstick era), for reference/rollback. Also on board flash as `config.yaml`. |

## Config highlights (and WHY — hard-won lessons)

| Setting | Value | Why |
|---|---|---|
| `stepping.engine` | `I2S_STATIC` | **Required.** `I2S_STREAM` breaks the TMC SPI chip-select on i2so pins → all drivers read `0x0` ("TMC driver not detected"). |
| Driver type | `tmc_5160` per motor | Chips verified TMC5160A-TA. |
| CS topology | **Independent CS**, `spi_index: -1` | X=`i2so.3`, Y=`i2so.6`, Z=`i2so.11`, Y2=`i2so.14`. NOT daisy-chain (that's for PiBot's external SilentStep drivers only). |
| `r_sense_ohms` | `0.075` | BTT TMC5160T Pro sense resistor (max 3.1 A RMS). |
| `run_amps` / `hold_amps` | `1.8` / `0.9` | 2.8 A peak ≈ 2.0 A RMS; 1.8 = ~90% safe start. Can raise to 2.0 for aluminum if temps allow. |
| `run_mode` | `CoolStep` | Full torque + adaptive current (mills aluminum). StealthChop rejected — too weak at speed. |
| `homing_mode` | `StallGuard` | Sensorless homing. FluidNC switches chopper during homing automatically. |
| `homing_runs` | `1` | **Required for sensorless.** The 2nd confirmation touch can't re-detect a stall in ~1 mm → Alarm 9. |
| `idle_disable` | `false` | Motors hold position at idle (Z won't drop, axes can't be pushed). |
| Direction pins | X/Y/Y2 inverted (`:low`), Z not | Matches machine wiring. Y and Y2 flipped together (gantry stays in sync). |
| X/Y accel / max | 500 mm/s² / 6000 mm/min | 2000/15000 was violently jerky, and a 2.5 V motor @24 V can't sustain ~1900 RPM anyway. |
| Z accel / max | 300 / 3000 | Spindle-mass axis, keep gentle. |

## ⚠️ FluidNC config gotchas (will bite again if forgotten)

1. **NO trailing `#` comments** on value lines. This firmware's YAML parser folds the comment into the value — it silently turned `engine: I2S_STATIC  # comment` into `RMT`, and a comment containing "`I2SO.12:low`" **inverted a direction pin**. Full-line comments only.
2. **Board SPI-routing jumpers must be installed** (PiBot wiki "Point ⑲") to connect SCK/MOSI/MISO/CS to the driver sockets, microstep jumpers (Point ⑭) removed, logic-level jumper on **3V3**. Without ⑲: all drivers read `0x0`.
3. **Power sequence:** driver Vmot before main Vmot (PiBot doc). TMC5160 needs motor voltage present to even answer SPI (`0x0` otherwise).
4. Boot log (TMC detection lines) is only visible on the **WebUI/ncSender console or USB serial** — not over HTTP.

## Sensorless homing — the recipe (proven on X)

Per driver (BTT TMC5160T Pro):
1. **DIAG pins** = the two standalone pins on the module's TOP edge (DIAG0 = corner/square pad, DIAG1 = its neighbor). NOT part of the J1/J2 rows. Yellow jumper caps OFF.
2. Solder **10 kΩ from DIAG1 → VIO** on the module (VIO = right row, 7th pin, 3.3 V. **NEVER the nearby VM — that's 24 V and will kill the ESP32 input**). Datasheet: DIAG is open-drain, pull-up must be ≤47 k.
3. Wire **DIAG1 → the axis's limit input** (3-pin JST, signal pin):
   - X → io35, Y → io34, Z → io39, Y2 → io36
4. Config: limit pins are **active-low** (`gpio.xx:low`) because DIAG only *pulls low* on stall. gpio 34/35/36/39 are input-only with **no internal pull-ups** — hence the external resistors.
5. Homing feed = seek = 300 mm/min (StallGuard needs medium speed, equal rates). `stallguard: 5` threshold — lower = more sensitive, tune per axis with `stallguard_debug=true`.
6. Gantry auto-square: Y motor0 (io34) and Y2 motor1 (io36) each stop on their own stall.

**Failure signatures:** instant 1 mm + Alarm 8 = limit input floating/never clears (missing wire or pull-up). Alarm 9 after a good bounce = `homing_runs` still 2. Stops mid-travel = noise (missing pull-up) or threshold too sensitive.

## Ops — pushing a config change

```bash
# upload (from this directory)
curl -F "path=/" -F "myfile=@config-tmc5160.yaml;filename=/config-tmc5160.yaml" http://10.0.2.28/files
# verify byte-identical
curl -s http://10.0.2.28/config-tmc5160.yaml | diff config-tmc5160.yaml - && echo OK
# reboot to apply
curl "http://10.0.2.28/command?plain=%24Bye"
# confirm live values
curl -s "http://10.0.2.28/command?plain=%24Config%2FDump"
```

Active config selector: `$Config/Filename=config-tmc5160.yaml` (rollback: `=config.yaml`).

Live (no-reboot) tuning examples:
```
$/axes/x/motor0/tmc_5160/stallguard=8
$/axes/x/motor0/tmc_5160/stallguard_debug=true
```

## Status / TODO (as of 2026-07-22)

- [x] SPI comms to all 4 drivers (jumpers ⑲ installed)
- [x] Motion, directions, gang-Y sync, holding torque
- [x] Sensorless homing proven on X (jumper cap → wire + pull-up + `:low` + single run)
- [ ] Solder 4× 10 k VIO↔DIAG1 resistors; wire DIAG1 → io35/34/39/36
- [ ] Re-push `config-tmc5160.yaml` on next power-up (last push interrupted by power-off) and verify
- [ ] Test: `$HX` → `$HZ` → `$HY` (watch gantry squaring!) → full `$H`
- [ ] Tune `stallguard` per axis; verify new 500 mm/s² jog feel
- [ ] Optional: `run_amps` 1.8 → 2.0 for aluminum if motor temps OK
- [ ] Future: e-stop (hardware cutoff in Vmot line + optional `estop_pin`), spindle relay (gpio.26)
