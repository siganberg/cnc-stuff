# SLB-EXT firmware — Virtual Inputs plugin

grblHAL builds for the **Sienci SLB-EXT** including the
[Virtual Inputs plugin](https://github.com/siganberg/grblhal-virtual-inputs).

The plugin adds a **virtual probe** and **virtual toolsetter** — machine inputs
asserted by software instead of by a GPIO pin, so a sender or a wireless probe
can stop a `G38` cycle over the connection it already has. It merges into the
hardware probe inside the stepper interrupt, so the controller cannot tell a
virtual assert from a real pin transition.

The plugin is now registered in grblHAL upstream (`plugins_init.h`) and
available in the grblHAL Web Builder.

## ⚠ Experimental — read before flashing

- **No warranty.** Personal builds, not Sienci releases. Not affiliated with or
  supported by Sienci Labs or the grblHAL project. Do not report issues with
  these to either.
- **A virtual probe bypasses your physical probe wiring.** If whatever asserts
  it stalls, disconnects or drops a packet, **the probe move will not stop** and
  the tool drives on to the end of its programmed travel. Treat wireless links
  as unreliable.
- **Virtual inputs are level-held, not one-shot.** They stay asserted until
  released (`0xA6`/`0xA8`/`0xA9`) or a soft reset. The host owns the release —
  a stale assert will fail the next probe's initial check with `ALARM:4`.
- **Test clear of the bed**, at low feed, with a hand on the E-stop.
- **These carry a specific machine's defaults** — travels 1260 × 1248 × 170,
  4 axes with Y auto-square, steps/mm 320/320/200, and a particular spindle
  setup. Stored settings survive a flash, but `$RST=*` would load *those*
  defaults, not yours. Back up `$$` first.
- Flashing instructions and DFU recovery are in the
  [repository root README](../../../../README.md).

## Which one

| File | Toolsetter |
|---|---|
| `firmware_virtual-inputs_v0.05_20260811.hex` | shared with the probe (stock SLB behaviour) |
| `firmware_virtual-inputs_v0.05_toolsetter-probe_20260811.hex` | separate probe, `TOOLSETTER_ENABLE=1` |

**Take the first one unless you specifically want a virtual toolsetter.** It is
strictly additive: nothing about existing probe or toolsetter behaviour changes.

The second registers the toolsetter as its own selectable probe. That
**disables the SLB Probing mux**, so the physical toolsetter no longer fires on
a bare `G38` — it needs `G38.x P1`. Existing toolchange macros would need
updating.

| | md5 |
|---|---|
| `..._v0.05_20260811.hex` | `1f297dd3cb30784b8e2afbbe96872b9a` |
| `..._v0.05_toolsetter-probe_20260811.hex` | `9e21341ba5c6dce25189360920a4b650` |

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
$I        → [PLUGIN:Virtual inputs v0.05]
$VI       → [VINPUTS:PROBE=0,TLS=0]
            [VINPUTCNT:PROBE_SET=0,PROBE_CLR=0,TLS_SET=0,TLS_CLR=0]
$VI=0,1   assert probe        $VI=0,0  release
$VI=1,1   assert toolsetter   $VI=1,0  release
$VI=RST   zero the counters (states left alone)
```

`[VINPUTCNT:...]` counts every command byte the controller actually processed,
so you can compare it against what your host thinks it sent and measure loss on
the serial link.

Virtual inputs are cleared only on **soft reset** — not on probe completion.
That is deliberate: clearing per cycle broke seek-then-probe-away, because the
input read as released between the two moves while the sensor was still
mechanically pressed.

## Test status

The probe merge is verified on an SLB-EXT in the shared topology — physical
toolsetter `G38.2` then `G38.4`, and virtual probe `0xA5` / `G38.5` / `0xA6`,
both stopping correctly and latching a probe position.

The plugin also carries a host-side regression suite (174 checks) covering both
topologies, both probe directions and all four contact sources:
`./test/run.sh` in the plugin repo.

The **separate-probe** variant builds clean but has **not** been run on a
machine.

## Build details

| | |
|---|---|
| grblHAL core | build `20260811` (`29b7471`) |
| Driver | [grblHAL/STM32F4xx](https://github.com/grblHAL/STM32F4xx), `BOARD_LONGBOARD32_EXT` |
| MCU | STM32F412VG |
| Base config | grblHAL Web Builder job for this machine |
| Plugin | [siganberg/grblhal-virtual-inputs](https://github.com/siganberg/grblhal-virtual-inputs) v0.05 |

Core `20260811` also carries Terje's fix for parking retract, which was broken
for all non-laser machines in earlier builds — safety-door and sleep parking
silently did nothing but de-energise.

No core or driver source is modified; the plugin is enabled with
`-D VIRTUAL_INPUTS_ENABLE=1` and registered by the core itself.
