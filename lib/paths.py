"""paths.py - where the simulator is.

The tests run the firmware in rtlsim, from an ovs-rtlpg checkout
(github.com/sirmick/ovs-rtlpg): $RTLSIM_OVS, else ovs-rtlpg beside this
repository. Its build/rtlsim is the simulator ($RTLSIM overrides it), its
boards/ the board files, its tools/ (simconsole.py, rtlswitch.py) and tests/
(rtlsim_ctl.py) the libraries
the tests use.

The firmware is RTLPlayground: $RTLPG, else RTLPlayground beside this
repository.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lib"))
import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OVS = os.path.abspath(os.environ.get("RTLSIM_OVS") or os.path.join(os.path.dirname(ROOT), "ovs-rtlpg"))
RTLSIM = os.environ.get("RTLSIM") or os.path.join(OVS, "build", "rtlsim")
RTLPG = os.path.abspath(os.environ.get("RTLPG") or os.path.join(os.path.dirname(ROOT), "RTLPlayground"))

for d in (os.path.join(OVS, "tools"), os.path.join(OVS, "tests")):
    if d not in sys.path:
        sys.path.append(d)
