# SLB-EXT firmware — Virtual Inputs plugin

grblHAL builds for the **Sienci SLB-EXT** including the
[Virtual Inputs plugin](https://github.com/siganberg/grblhal-virtual-inputs).

The plugin adds a **virtual probe** and **virtual toolsetter** — machine inputs
asserted by software instead of by a GPIO pin, so a sender or a wireless probe
can stop a `G38` cycle over the connection it already has. It merges into the
hardware probe inside the stepper interrupt, so the controller cannot tell a
virtual assert from a real pin transition.

## ⚠ Experimental — read before flashing

- **No warranty.** These are personal builds, not Sienci releases. Not
  affiliated with or supported by Sienci Labs or the grblHAL project. Do not
  report issues with these to either.
- **A virtual probe bypasses your physical probe wiring.** If whatever asserts
  it stalls, disconnects or drops a packet, **the probe move will not stop** and
  the tool drives on to the end of its programmed travel. Treat wireless links
  as unreliable.
- **Test clear of the bed**, at low feed, with a hand on the E-stop.
- **These carry a specific machine's defaults** — travels 1260 × 1248 × 170,
  4 axes with Y auto-square, steps/mm 320/320/200, and a particular spindle
  setup. Settings already stored in NVS are preserved on flash, but a settings
  reset (`$RST=*`) will load *those* defaults, not yours. Back up your settings
  first (`$$`).
- Keep a known-good firmware handy. Flashing instructions and DFU recovery are
  in the [repository root README](../../../../README.md).

## Which one

| File | Toolsetter | Hardware tested |
|---|---|---|
| `firmware_virtual-inputs_20260805.hex` | shared with probe (stock SLB behaviour) | ✅ yes |
| `firmware_virtual-inputs_toolsetter-probe_20260805.hex` | separate probe, `TOOLSETTER_ENABLE=1` | ❌ **not tested** |

**Take the first one unless you specifically want a virtual toolsetter.** It is
strictly additive: nothing about existing probe or toolsetter behaviour changes.

The second build registers the toolsetter as its own selectable probe. That
**disables the SLB Probing mux**, so the physical toolsetter no longer fires on
a bare `G38` — it needs `G38.x P1`. Any existing toolchange macro relying on the
old behaviour will need updating. It compiles and links but has not been run on
a machine.

| | md5 |
|---|---|
| `firmware_virtual-inputs_20260805.hex` | `b54f5f9e618588df32009e9fddca0890` |
| `firmware_virtual-inputs_toolsetter-probe_20260805.hex` | `19f6ec47dbb1edbe714bdf95b9921271` |

## Commands

Single raw bytes, no newline. Handled in the serial RX interrupt, so they work
**during** a probe move — `$` commands do not, because grblHAL stops parsing
lines while a `G38` is running.

| Byte | Action |
|---|---|
| `0xA5` | assert probe |
| `0xA6` | release probe |
| `0xA7` | assert toolsetter |
| `0xA8` | release toolsetter |
| `0xA9` | release all |

ncSender's console accepts `0xA5` typed directly and converts it to the raw
byte. Sending it from your own code needs a real byte — a string goes out
UTF-8-encoded as `0xC2 0xA5` and never arrives.

Bench commands (not usable mid-probe):

```
$I        → [PLUGIN:Virtual inputs v0.02]
$VI       → [VINPUTS:PROBE=0,TLS=0]
$VI=0,1   assert probe        $VI=0,0  release
$VI=1,1   assert toolsetter   $VI=1,0  release
```

Virtual inputs clear automatically on probe completion and on soft reset.

## What was verified

On an SLB-EXT running the shared-toolsetter build, `G38.3`/`G38.5 X-10 F100`:

| | |
|---|---|
| virtual toolsetter, `0xA7` | `[PRB:587.037,…:1]` stopped at 6.70 mm |
| virtual probe, `0xA5` | `[PRB:580.331,…:1]` stopped at 6.70 mm |
| probe-away, `0xA5` then `0xA6` | `[PRB:573.684,…:1]` stopped at 6.65 mm |

The `:1` is grblHAL's probe-success flag — the core ran a full probe cycle and
latched a position, rather than merely halting.

## Build details

| | |
|---|---|
| grblHAL core | build `20260803` (`b34eabe`) |
| Driver | [grblHAL/STM32F4xx](https://github.com/grblHAL/STM32F4xx), `BOARD_LONGBOARD32_EXT` |
| MCU | STM32F412VG |
| Base config | grblHAL Web Builder job for this machine |
| Plugin | [siganberg/grblhal-virtual-inputs](https://github.com/siganberg/grblhal-virtual-inputs) |

No core or driver source was modified. The plugin attaches through the core's
weak `my_plugin_init()` hook, and the only other change is the
`TOOLSETTER_ENABLE=1` build flag in the second variant.
