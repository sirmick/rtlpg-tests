# rtlpg-tests

The tests of [RTLPlayground](https://github.com/sirmick/RTLPlayground)'s
firmware: the real image, unmodified, run in rtlsim, the RTL837x simulator of
[ovs-rtlpg](https://github.com/sirmick/ovs-rtlpg). The simulator stays a model
of the chip and the firmware stays firmware; what the firmware must do is here.

They came out of ovs-rtlpg's `tests/` with their history. ovs-rtlpg keeps the
simulator's own tests (the CPU, banking, the flash model, control mode).

## Both firmwares

The fork has three branches, and two command lines:

| Branch | CLI |
|---|---|
| `compact-layout`, `feat/sched` | the old commands: `vlan 10 2 3`, `pvid 2 10`, `lacp show`, JSON pages |
| `main` | the object model: `set vlan.10.members 2,3`, `apply`, `get state.lacp.port`, `POST /cli` |

The switch behaves the same either way, so the same test runs on both. A test
says what it wants in the old commands, and `lib/fwcli.py` types it in the
CLI the image has: as it is on an old image, as the `set`/`apply` lines on an
object-model one (it answers `get port.1.pvid`). Reads go the same way:
`fwcli.read("l2")` is `{path: value}` from either image. The mapping is
`oldnew/translate.py`, the one the old-vs-new harness compares images by.

## Running

Beside this checkout: an RTLPlayground checkout, built (`make MACHINE=SWGT024_V2_0_UNMANAGED LAYOUT=compact`),
and ovs-rtlpg with `make build/rtlsim`. Elsewhere: `RTLPG=` and `RTLSIM_OVS=`.

    make core       # no privilege: boot vs silicon, NIC, flows, resets, NIC ring, LACP, holds
    make net        # sudo + Open vSwitch: Linux in netns, switching, two switches, IGMP vs silicon
    make update     # sudo: a web update on a persistent flash, a power cut in it
    make powercut   # a power cut at every step of a web install
    make flash      # the image matrix ($RTLSIM_IMAGES, RTLPlayground's make rtlsim-images)
    make vm         # the switch VM under QEMU
    make oldnew OLD=... NEW=...   # two images, the same scenarios, compared (oldnew/README.md)

Every test of a tier runs, and the tier fails if any did. `ci/run.sh RTLPG OVS [TIER...]`
is what RTLPlayground's CI runs.

These tests are functional, not timing-faithful: rtlsim's flash and clock
aren't the chip's. A pass says the logic and the flash contents are right, not
that an update is safe on a real switch. The bench is the last gate.

## Layout

| Where | What |
|---|---|
| `lib/` | `paths.py` (where ovs-rtlpg and RTLPlayground are), `console.py` (what the firmware's console looks like: prompt, address, MAC, the switch-init write), `fwcli.py` (the two CLIs) |
| `fw/` | the boot against silicon, LACP, the NIC ring, the console ring, control mode's holds |
| `net/` | Linux against the firmware: TCP/IP, switching, topologies, IGMP, loop detection, uIP hardening, web update; `hardware/` the same probes for a real switch |
| `fabric/` | the flows the firmware's configurations compile to, against goldens |
| `flash/` | installs, power cuts, the loader, standard to compact, PoE |
| `oldnew/` | the old-vs-new harness and its translation table |
| `vm/` | the switch VM booting the image |
| `ci/run.sh` | the tiers, as CI runs them |

## Licence

MIT (`LICENSE`).
