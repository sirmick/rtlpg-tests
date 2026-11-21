"""console.py - the firmware's serial console, as the tests see it.

ovs-rtlpg's tools/simconsole.py runs rtlsim with its UART on a pipe and knows
nothing of the firmware; what RTLPlayground's console looks like is here:
its prompt, its default address, the MAC its boot reports.
"""
import re

import paths  # noqa: F401  (ovs-rtlpg's tools/ on sys.path)
from simconsole import Console  # noqa: F401  (the tests' import of it)

# The prompt either firmware ends a reply with: "\n> ", and the object
# model's "*> " (the candidate differs) and "[confirm N] " (a window open)
PROMPT = re.compile(rb"\n(\[confirm [0-9]+\] )?\*?> ")

# config.txt's address, on every branch of the fork
DEFAULT_IP = "192.168.10.247"

# The write that ends RTLPlayground's switch init, for rtlsim's early-reset
# hang (--control has it on; with no --switch-init it never fires): the last
# step of rtl8373_init()/rtl8372_init(), after the PHY and SerDes set-up, a
# write to 0x632c (MAC access) with bits 16-20 set. The loader's own network
# set-up sets only bits 16-19 there. A reset by the application before it
# hangs the chip, as an RTL8373 did on the bench.
SWITCH_INIT = ["--switch-init", "632c:1f0000"]


def switch_ip(console, timeout=10):
    """The firmware's management address, from its CLI (lib/fwcli.py: either
    firmware's), so a test works whatever address the image carries."""
    import fwcli
    return fwcli.FwCli(fwcli.console_sender(console, timeout)).read("ip").get("state.mgmt.ip") or DEFAULT_IP


def peer_ip(switch_ip):
    """An address on the switch's /24 for the test peer to use."""
    return re.sub(r"\.\d+$", ".2" if switch_ip.endswith(".1") else ".1", switch_ip)


def boot_mac(console):
    """The MAC the firmware gave itself at boot (its "Setting MAC to:" line)."""
    m = re.search(rb"Setting MAC to: ([0-9a-fA-F:]{17})", console.log)
    return m.group(1).decode().lower() if m else None
