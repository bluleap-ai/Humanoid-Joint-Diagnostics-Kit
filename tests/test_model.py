import pytest
from can_tool.protocol import Frame, Packet, Kind, EXT, configuration
from can_tool.model import (
    DisplayFilter,
    Decoder,
    SequenceTracker,
    Monitor,
    AdapterQueue,
    DiagnosticAdapter,
)
from can_tool.recording import Recorder, read_recording, export_csv
from can_tool.simulator import SimState


def test_filter_formats_and_ranges():
    filt = DisplayFilter("0x100-0x200", "0x150", extended=False, names=["Status"])
    assert filt.matches(Frame(0x100), "Status")
    assert not filt.matches(Frame(0x150), "Status")
    assert not filt.matches(Frame(0x100, flags=EXT), "Status")
    assert not filt.matches(Frame(0x100), "Other")


def test_sequences_and_session_change():
    t = SequenceTracker()
    assert t.observe(Frame(1, sequence=1, session=1)) == 0
    assert t.observe(Frame(1, sequence=4, session=1)) == 2
    assert t.observe(Frame(1, sequence=1, session=2)) == 0
    with pytest.raises(ValueError):
        t.observe(Frame(1, sequence=1, session=2))


def test_dbc():
    d = Decoder("examples/synthetic.dbc")
    f = d.encode("Status", {"Counter": 42, "Temperature": -12.3, "Mode": "Running"})
    name, signals, error = d.decode(f)
    assert not error and name == "Status"
    assert signals["Counter"]["value"] == 42
    assert signals["Temperature"]["value"] == pytest.approx(-12.3)
    assert signals["Mode"]["value"] == "Running"
    for name, values in [
        ("Multiplexed", {"Selector": 1, "Speed": 12.5}),
        ("Multiplexed", {"Selector": 2, "Torque": -1.25}),
        ("BigEndian", {"Signed": -17}),
    ]:
        _, decoded, error = d.decode(d.encode(name, values))
        assert not error
        for k, v in values.items():
            assert decoded[k]["value"] == v
    assert d.decode(Frame(0x100, b""))[2]
    assert d.decode(Frame(0x100, b"12345678", EXT))[0] == ""


def test_recording(tmp_path):
    path = tmp_path / "r.jsonl"
    f = Frame(1, b"123", sequence=3, session=9)
    with Recorder(path, {"synthetic": True}) as r:
        r.write("rx", f.as_dict(), 12)
        r.write("status", {"hardware_rx_losses": None})
        r.write("tx_event", {"state": "completed"})
    events = list(read_recording(path))
    assert Frame.from_dict(events[1]["data"]) == f
    out = tmp_path / "out.csv"
    export_csv(path, out)
    assert "313233" in out.read_text()
    with pytest.raises(FileExistsError):
        Recorder(path, {})
    path.write_text(
        '{"type":"metadata","data":{"format":"wireless-can-jsonl","version":2}}\n'
    )
    with pytest.raises(ValueError):
        list(read_recording(path))


def test_slow_adapter_and_bounded_model():
    q = AdapterQueue(2)
    for i in range(100):
        q.publish(i)
    assert q.discards == 98 and q.queue.qsize() == 2
    m = Monitor(3)
    for i in range(10):
        m.add(Frame(i))
    assert len(m.latest) == len(m.trace) == 3
    m.add(Frame(9, flags=EXT))
    assert len(m.latest) == 3


def test_simulated_overflow_and_ownership():
    s = SimState(2)
    s.connect("a")
    s.running = True
    for _ in range(5):
        s.receive()
    assert s.sequence == 5 and s.enqueued == 2 and s.drops == 3
    with pytest.raises(PermissionError):
        s.connect("b")
    assert not s.command("b", Packet(Kind.START, 1, s.session))["ok"]
    s.disconnect("a")
    assert s.discards == 2 and not s.active


def test_simulated_duplicates_cancel_reconnect():
    s = SimState()
    s.connect("a")
    s.command("a", Packet(Kind.CONFIGURE, 1, s.session, configuration(active=True)))
    s.command("a", Packet(Kind.START, 2, s.session))
    tx = Packet(Kind.TX, 3, s.session, Frame(1, b"1").tx_wire(10, 5))
    assert s.command("a", tx)["ok"]
    assert s.command("a", tx)["ok"]
    assert s.executions == 1
    assert not s.command("a", Packet(Kind.TX, 3, s.session, Frame(2).tx_wire()))["ok"]
    assert s.command("a", Packet(Kind.CANCEL, 4, s.session))["ok"]
    assert s.pending is None
    s.disconnect("a")
    s.connect("b")
    assert not s.command("b", Packet(Kind.TX, 1, s.session, Frame(1).tx_wire()))["ok"]


def test_recording_failure_is_explicit(tmp_path):
    r = Recorder(tmp_path / "fail.jsonl", {})
    r.file.close()

    class FailedDisk:
        def write(self, data):
            raise OSError("disk full")

    r.file = FailedDisk()
    with pytest.raises(OSError):
        r.write("rx", Frame(1).as_dict())
    assert r.failures == 1


def test_lease_expires_without_resuming_active():
    s = SimState()
    s.connect("a")
    s.active = s.running = True
    s.pending = [1, 5, 10, 0, 0]
    s.lease = 0
    s.tick()
    assert s.pending is None and not s.running and not s.active


def test_adapter_gate():
    class Owner:
        def send_frame(self, f):
            return f

    adapter = DiagnosticAdapter(Owner())
    with pytest.raises(PermissionError):
        adapter.send(Frame(1))
    assert adapter.send(Frame(1), allow_tx=True) == Frame(1)
