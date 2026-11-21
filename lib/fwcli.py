"""fwcli.py - a test's settings, typed in the CLI the image has.

A test says what it wants in the old commands (`vlan 10 office 1 2t`,
`pvid 3 10`, `isolate 1 3`, `igmp on`). On an image older than the object
model (compact-layout, feat/sched) they are typed as they are. On an
object-model image (main: it answers `get port.1.pvid`) each becomes the
`set`/`del` lines oldnew/translate.py gives for it, then `apply`; the
lines are the same mapping oldnew compares old and new images by, so a test
and oldnew can't disagree on what an old command means.

    cli = FwCli(send, board)	# send(line) -> the reply, up to the prompt
    cli.config("vlan 20 1t 3t", "pvid 2 10")
    cli.get("state.l2")		# {path: value}, an object-model image only

send(line) is the test's own console: the tests drive several kinds
(fw/console.py's Console, rtlswitch's labs, oldnew's bench).
"""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "oldnew"))
import paths  # noqa: E402,F401  (ovs-rtlpg's libraries on sys.path)
import translate  # noqa: E402

PROBE = "get port.1.pvid"


def is_om(reply):
    """Whether PROBE's reply is an object-model image's."""
    return "port.1.pvid " in (reply or "")


class Ports:
    """The board's ports as translate.py's rows want them (oldnew.Run's)."""
    def __init__(self, board):
        ports = json.load(open(board or os.path.join(paths.OVS, "boards", "swgt024_v2_0_unmanaged.json")))["ports"]
        copper = [p for p in ports if "sfp" not in p]
        self.P = [p["phys"] for p in copper]
        self.F = [p["front"] for p in copper]
        self.cages = {p["sfp"]["slot"]: (p["phys"], p["front"]) for p in ports if "sfp" in p}


class Refused(Exception):
    pass


class FwCli:
    def __init__(self, send, board=None, om=None):
        self.send = send
        self.r = Ports(board)
        self.om = is_om(send(PROBE)) if om is None else om
        self.canon = translate.objects()

    def lines(self, old):
        """What to type for one old line on this image."""
        if not self.om:
            return [old]
        t = translate.find(old, self.canon)
        if t is None:
            raise Refused(f"fwcli: {old!r} has no object-model form in translate.py")
        m, what = t
        if not isinstance(what, translate.Set):
            raise Refused(f"fwcli: {old!r} isn't a setting (translate.py has it as {type(what).__name__})")
        prev = None
        if what.before:
            prev = translate.normalized(translate.values("".join(self.send(f"get {p}") for p in what.before(m, self.r))))
        v = what.vals(m, self.r, prev)
        out = [f"del {p}" if x is translate.DEL else f"set {p} {x}" for p, x in v.items()]
        return out + (list(what.then(m, self.r, prev)) if what.then else [])

    def config(self, *old):
        """Each old line, in this image's CLI; on an object-model image the
        sets go together, then one apply. Raises Refused on an err."""
        if not self.om:
            return [self.send(l) for l in old]
        sets, after = [], []
        for l in old:
            for x in self.lines(l):
                (after if x.startswith("do ") else sets).append(x)
        out = []
        for x in sets + ["apply"] + after:
            reply = self.send(x)
            out.append(reply)
            if re.search(r"^err ", reply or "", re.M):
                raise Refused(f"fwcli: {x!r}: {reply.strip()}")
        return out

    def cmd(self, line):
        """One old line, for a test that mixes settings with commands both
        firmwares share (regget, regset): a setting the image has on the
        object model goes as config(), anything else is typed as it is."""
        if self.om:
            t = translate.find(line, self.canon)
            if t and isinstance(t[1], translate.Set):
                return "".join(self.config(line))
        return self.send(line)

    def get(self, path):
        """{path: value} of a get (object-model images)."""
        return translate.values(self.send(f"get {path}"))

    def read(self, old):
        """An old printer (`l2`, `lacp show`, `sfp`, `ip`) as {path: value},
        on either image: the old one's text parsed by translate.py's row, the
        new one's gets for the same paths, both normalized the same way."""
        t = translate.find(old, self.canon)
        if t is None or not isinstance(t[1], translate.Read):
            raise Refused(f"fwcli: {old!r} isn't a printer translate.py reads")
        m, what = t
        if self.om:
            objs = what.objs & self.canon	# a template with no design object has None
            text = "".join(self.send(g) for g in what.gets(m, self.r, objs))
            v, _ = what.new(text, m, self.r, objs)
        else:
            v, _ = what.parse(self.send(old), m, self.r)
        return what.post(v, m, self.r)


# An object-model prompt: "*> " while the candidate differs, "[confirm N] "
# in a window. The old firmware's is "\n> ".
PROMPT = re.compile(rb"\n(\[confirm \d+\] )?\*?> $")


def console_sender(c, timeout=10):
    """send(line) for a fw/console.py Console (rtlswitch's labs have one):
    the reply up to the next prompt, either firmware's."""
    def send(line):
        start = len(c.log)
        c.send(line)
        end = time.time() + timeout
        while time.time() < end:
            if not c.expect(b"> ", max(0.1, end - time.time())):
                break
            if PROMPT.search(c.log[start:]):
                break
        return c.log[start:].decode(errors="replace")
    return send
