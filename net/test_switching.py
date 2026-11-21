#!/usr/bin/env python3
"""test_switching.py - the front ports switch, as the firmware configures them.

    net/test_switching.py IMAGE [--rtlsim build/rtlsim]

Three Linux hosts on front ports 1-3 of a switch on OVS (tools/rtlswitch.py),
configured only through the firmware's CLI
(lib/fwcli.py: the old commands, or their set/apply on an object-model image). Checks:
- hosts reach each other through the bridge, and the firmware's l2 command
  shows their MACs, learned on their ports;
- a known unicast doesn't flood: the third host doesn't see it;
- port isolation (isolate 1 3): port 1 reaches port 3 but not port 2; off again;
- VLANs: PVID 10 on ports 2 and 3 (vlan 10 2 3) splits them from port 1,
  and a tagged VLAN (vlan 20 1t 3t) carries 802.1Q between hosts 1 and 3;
- ageing (--ageing 3): learned entries leave the l2 table once idle.
Needs sudo; skipped without it.
"""
import argparse, os, re, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lib"))
import paths
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../fw"))
sys.path.insert(0, os.path.join(paths.OVS, "tools"))
from console import PROMPT
import fwcli
from rtlswitch import Lab
from privovs import sudo

failures = 0
HOSTS = {"1": "192.168.2.11", "2": "192.168.2.12", "3": "192.168.2.13"}


def check(cond, msg):
    global failures
    print(("PASS  " if cond else "FAIL  ") + msg)
    failures += not cond


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--rtlsim", default=paths.RTLSIM)
    a = ap.parse_args()
    if subprocess.run(["sudo", "-n", "true"], capture_output=True).returncode:
        print("switching: no passwordless sudo, skipped")
        return 0

    lab = Lab(a.image, name=f"t{os.getpid() % 100000}", hosts={f: f"{ip}/24" for f, ip in HOSTS.items()},
              extra=["--ageing", "3", "--trace-of"],
              rtlsim=a.rtlsim, console=True, stderr=open(os.devnull, "w"))
    c = None

    def nsx(front, *cmd, check=False):
        return sudo("ip", "netns", "exec", lab.host_ns(front), *cmd, check=check, timeout=30)

    def ping(src, dst_ip, n=2):
        return nsx(src, "ping", "-c", str(n), "-i", "0.2", "-W", "1", dst_ip).returncode == 0

    def l2():	# the l2 table, as "path value" text, either firmware's
        return "\n".join(f"{p} {v}" for p, v in fw.read("l2").items())

    try:
        lab.start(attach=False)
        c = lab.console
        check(c.expect(PROMPT, 30), "boots to the prompt")
        fw = fwcli.FwCli(fwcli.console_sender(c))
        macs = {}
        for f in HOSTS:
            for sysctl in ("net.ipv6.conf.all.disable_ipv6=1", "net.ipv6.conf.default.disable_ipv6=1"):
                nsx(f, "sysctl", "-q", "-w", sysctl)
            m = re.search(r"link/ether ([0-9a-f:]+)", nsx(f, "ip", "link", "show", "eth0").stdout)
            macs[f] = m.group(1) if m else "?"
        lab.attach()
        time.sleep(1)

        check(ping("1", HOSTS["2"]) and ping("1", HOSTS["3"]) and ping("2", HOSTS["3"]),
              "hosts on ports 1, 2 and 3 reach each other through the bridge")
        table = l2()
        rows = {f: re.search(re.escape(mac) + r".*", table) for f, mac in macs.items()}
        check(all(rows.values()), "the firmware's l2 table has the three hosts' MACs: "
              + "; ".join(r.group(0).strip() for r in rows.values() if r))

        sniff = subprocess.Popen(["sudo", "-n", "ip", "netns", "exec", lab.host_ns("3"), "tcpdump", "-l", "-n", "-i",
                                  "eth0", "icmp"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        time.sleep(1)
        ok = ping("1", HOSTS["2"], 5)
        time.sleep(0.5)
        sniff.terminate()	# sudo passes it on to tcpdump
        seen = sniff.communicate()[0]
        check(ok and HOSTS["2"] not in seen, f"a known unicast doesn't flood: port 3 sees none of 1 -> 2's pings"
              + ("" if HOSTS["2"] not in seen else f" ({seen.count(chr(10))} lines)"))

        fw.config("isolate 1 3")
        check(not ping("1", HOSTS["2"]) and ping("1", HOSTS["3"]),
              "isolate 1 3: port 1 reaches port 3, not port 2")
        fw.config("isolate 1 off")
        check(ping("1", HOSTS["2"]), "isolate 1 off: port 1 reaches port 2 again")

        fw.config("vlan 10 2 3", "pvid 2 10", "pvid 3 10")
        check(ping("2", HOSTS["3"]) and not ping("1", HOSTS["2"]) and not ping("1", HOSTS["3"]),
              "PVID 10 on ports 2 and 3: they reach each other, not port 1")

        fw.config("vlan 20 1t 3t")
        for f, ip in (("1", "10.0.20.1/24"), ("3", "10.0.20.3/24")):
            nsx(f, "ip", "link", "add", "link", "eth0", "name", "eth0.20", "type", "vlan", "id", "20", check=True)
            nsx(f, "ip", "addr", "add", ip, "dev", "eth0.20", check=True)
            nsx(f, "ip", "link", "set", "eth0.20", "up", check=True)
        check(ping("1", "10.0.20.3"), "VLAN 20 tagged on ports 1 and 3: 802.1Q frames get through")

        t = time.time()		# OVS checks idle timeouts about once a second
        while time.time() - t < 10:
            table = l2()
            if not any(mac in table for mac in macs.values()):
                break
            time.sleep(1)
        check(not any(mac in table for mac in macs.values()), f"ageing (3 s): the learned MACs leave the l2 table "
              f"{time.time() - t:.0f} s after the traffic stops")
    finally:
        lab.stop()

    print(f"test_switching: {'ALL PASS' if not failures else f'{failures} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
