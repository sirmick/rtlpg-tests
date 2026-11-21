# rtlpg-tests - RTLPlayground's firmware, tested in rtlsim.
#
#   make TIER [RTLPG=...] [RTLSIM_OVS=...] [FW_MACHINE=... FW_BOARD=...]
#
# RTLPG is a built RTLPlayground checkout, RTLSIM_OVS an ovs-rtlpg checkout
# with build/rtlsim (lib/paths.py: both default to the checkout beside this
# one). Every test of a tier runs, and the tier fails if any did.
#
# A test drives the image in the CLI it has: an object-model image (main) is
# asked `get`, takes `set`/`apply`, and an older one (compact-layout,
# feat/sched) its own commands. oldnew/translate.py has the mapping.

RTLPG ?= $(abspath ../RTLPlayground)
RTLSIM_OVS ?= $(abspath ../ovs-rtlpg)
RTLSIM ?= $(RTLSIM_OVS)/build/rtlsim
export RTLPG RTLSIM_OVS RTLSIM
PY = python3

# The firmware: the newest compact build of FW_MACHINE, and its boot image.
# Another machine needs its board file, e.g. the 8x:
#   make core FW_MACHINE=KEEPLINK_KP_9000_9XHPML_V1_2 FW_BOARD=$(RTLSIM_OVS)/boards/keeplink_kp_9000_9xhpml_v1_2.json
FW_MACHINE ?= SWGT024_V2_0_UNMANAGED
FW_IMAGE ?= $(firstword $(shell ls -t $(RTLPG)/output/$(FW_MACHINE)-compact/rtlplayground-v*-compact.bin 2>/dev/null))
FW_BOOT_IMAGE ?= $(firstword $(shell ls -t $(RTLPG)/output/$(FW_MACHINE)-compact/rtlplayground-boot-v*-compact.bin 2>/dev/null))
FW_BOARD ?=
FWB = $(if $(FW_BOARD),--board $(FW_BOARD))
FW_OLD ?= $(FW_IMAGE)

# run each test in $(1), then fail if any did
define each
	@fails=0; for t in $(1); do echo "+ $$t"; $(PY) $$t || { fails=$$((fails + 1)); echo "FAILED: $$t"; }; done; \
	echo "$@: $$fails failed"; [ $$fails -eq 0 ]
endef

.PHONY: unit core net update powercut flash vm oldnew oldnew-checks need-image

need-image:
	@test -n "$(FW_IMAGE)" || { echo "no firmware image: build RTLPlayground ($(RTLPG)) or set FW_IMAGE"; exit 2; }

# The harness's own tests, no rtlsim
unit:
	$(call each,oldnew/test_known.py oldnew/test_translate.py oldnew/test_bench.py)

# No privilege, no image matrix: the boot against silicon, the NIC, L2
# ageing, the flow goldens, an install's resets, the NIC ring, LACP, and
# control mode's holds on the boot image
core: need-image unit
	$(call each,"fw/test_boot.py $(FW_IMAGE) $(FWB)" "net/test_nic.py $(FW_IMAGE) $(FWB)" \
		"net/test_l2_age.py $(FW_IMAGE) $(FWB)" "fabric/test_flows.py $(FW_IMAGE) $(FWB)" \
		"flash/test_boot0.py $(FW_IMAGE) $(FWB)" "fw/test_nic_ring.py $(FW_IMAGE) $(FWB)" \
		"fw/test_lacp.py $(FW_IMAGE) $(FWB)" $(if $(FW_BOOT_IMAGE),"fw/test_holds.py $(FW_BOOT_IMAGE) $(FWB)"))

# Linux in a network namespace against the firmware (sudo, OVS): over a tap
# and over OVS, switching, two switches cabled, IGMP snooping against silicon
net: need-image
	$(call each,"net/test_net.py $(FW_IMAGE) --via tap" "net/test_net.py $(FW_IMAGE) --via ovs" \
		"net/test_switching.py $(FW_IMAGE)" "net/test_topo.py $(FW_IMAGE)" "net/test_igmp.py $(FW_IMAGE)")

# A web update on a persistent flash, a power cut in the install (sudo; ~1.5 min)
update: need-image
	$(PY) net/test_update.py $(FW_IMAGE)

# A power cut at every step of a web install (no sudo; minutes, in parallel)
powercut: need-image
	$(PY) flash/test_powercut.py $(FW_IMAGE) --old $(FW_OLD)

# The image matrix ($RTLSIM_IMAGES; RTLPlayground's make rtlsim-images):
# PoE, standard -> compact, the loader, a web update through the loader
flash:
	$(call each,flash/test_pse.py flash/test_migrate.py flash/test_loader.py flash/test_loader_update.py)

# The switch VM (ovs-rtlpg's tools/vm) booting the image under QEMU, no root
vm: need-image
	$(MAKE) -C $(RTLSIM_OVS) vm FW_IMAGE=$(FW_IMAGE)
	$(PY) vm/test_vm.py

# Old vs new (oldnew/README.md): OLD and NEW boot images, compared on
# results; NEW_OM names the objects compared by value (oldnew/translate.py)
OLD ?= $(FW_BOOT_IMAGE)
NEW ?= $(OLD)
oldnew:
	$(PY) oldnew/oldnew.py --old $(OLD) --new $(NEW) $(if $(BOARD),--board $(BOARD)) \
		$(if $(EXPECT),--expect $(EXPECT)) $(if $(ONLY),--only $(ONLY)) \
		$(if $(NEW_PAYLOAD),--new-payload $(NEW_PAYLOAD)) $(if $(CHECKS),--checks) \
		$(if $(KNOWN),--known $(KNOWN)) $(if $(NEW_OM),--new-om $(NEW_OM)) $(if $(OLD_OM),--old-om $(OLD_OM))
oldnew-checks:
	$(PY) oldnew/checks.py --image $(NEW) $(if $(BOARD),--board $(BOARD)) $(if $(ONLY),--only $(ONLY)) \
		$(if $(KNOWN),--known $(KNOWN)) $(if $(NEW_OM),--om $(NEW_OM))
