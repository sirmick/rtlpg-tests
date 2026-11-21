#!/bin/bash
# run.sh - RTLPlayground's firmware through rtlsim, as CI runs it.
#
#   ci/run.sh RTLPG_DIR OVS_DIR [TIER ...]
#
# RTLPG_DIR is a built RTLPlayground checkout (its patched SDCC under
# toolchain/, a SWGT024_V2_0_UNMANAGED compact build in output/), OVS_DIR an
# ovs-rtlpg checkout. With no TIER it runs them all:
#
#   sim       build rtlsim; the simulator's own tests (ISA, banks, flash
#             busy, coverage, the flash model)              (no privilege)
#   core      the boot against silicon, the NIC, the flow goldens, an
#             install's resets, the NIC ring, LACP          (no privilege)
#   net       Linux in a netns: tap, OVS, switching, two switches, IGMP
#                                                           (sudo + openvswitch)
#   update    a web update on a persistent flash, its config kept, a power
#             cut in the copy                               (sudo)
#   powercut  a power cut at every step of a web install
#   flash     PoE, standard->compact, the loader, a web update through the
#             loader. Needs an image matrix in $RTLSIM_IMAGES (make
#             rtlsim-images); skipped, not failed, without one.
#   vm        the switch VM (ovs-rtlpg tools/vm) booting the image under QEMU
#
# These are functional tests, not silicon-timing-faithful: rtlsim's flash and
# clock are not the chip's, so a pass is not a green light to flash hardware.
# The bench is the final gate.
set -uo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
RTLPG=$(cd "${1:?usage: run.sh RTLPG_DIR OVS_DIR [TIER ...]}" && pwd)
OVS=$(cd "${2:?usage: run.sh RTLPG_DIR OVS_DIR [TIER ...]}" && pwd)
shift 2
TIERS=("$@"); [ ${#TIERS[@]} -eq 0 ] && TIERS=(sim core net update powercut flash vm)
export RTLPG RTLSIM_OVS=$OVS RTLSIM=$OVS/build/rtlsim
M="make -C $HERE RTLPG=$RTLPG RTLSIM_OVS=$OVS"
rc=0

run() {	# run NAME CMD...: groups the log, records a failure
	local name=$1; shift
	echo "::group::$name"
	if "$@"; then echo "--- $name: ok"; else rc=1; echo "::error::$name failed"; fi
	echo "::endgroup::"
}

echo "run.sh: RTLPG=$RTLPG OVS=$OVS"
ls "$RTLPG"/toolchain/sdcc-*/bin/sdcc >/dev/null 2>&1 || { echo "::error::no patched SDCC in $RTLPG/toolchain (build the firmware first)"; exit 2; }
make -C "$OVS" RTLPG="$RTLPG" -j build/rtlsim >/dev/null || { echo "::error::rtlsim did not build"; exit 2; }

for t in "${TIERS[@]}"; do
	case $t in
	sim)      run "the simulator's own tests" make -C "$OVS" RTLPG="$RTLPG" test ;;
	core)     run "core (boot, NIC, flows, resets, NIC ring, LACP)" $M core ;;
	net)      run "network (tap, OVS, switching, topology, IGMP)" $M net ;;
	update)   run "a web update on a persistent flash" $M update ;;
	vm)       run "the switch VM under QEMU" $M vm ;;
	powercut) run "power cut during a web install" $M powercut ;;
	flash)
		images=${RTLSIM_IMAGES:-$HOME/rtlsim/images}
		if ls "$images"/*/manifest.json >/dev/null 2>&1; then
			run "flash matrix (PoE, migrate, loader, loader update)" env RTLSIM_IMAGES="$images" $M flash
		else
			echo "flash matrix: no image set in $images (make rtlsim-images), skipped"
		fi ;;
	*) echo "::error::unknown tier $t"; rc=1 ;;
	esac
done

echo "run.sh: $([ $rc -eq 0 ] && echo PASS || echo FAILED)"
exit $rc
