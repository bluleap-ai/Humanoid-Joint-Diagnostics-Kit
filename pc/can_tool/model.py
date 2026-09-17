"""Bounded presentation, filtering, decoding and adapter fan-out."""

from collections import OrderedDict, deque
from queue import Queue, Full
from .protocol import EXT, FD, RTR


class SequenceTracker:
    def __init__(self):
        self.session = None
        self.last = None
        self.gaps = 0

    def observe(self, frame):
        if frame.session != self.session:
            self.session, self.last = frame.session, None
        gap = 0 if self.last is None else max(0, frame.sequence - self.last - 1)
        if self.last is not None and frame.sequence <= self.last:
            raise ValueError("non-increasing sequence within session")
        self.last = frame.sequence
        self.gaps += gap
        return gap


class DisplayFilter:
    def __init__(self, include="", exclude="", extended=None, names=()):
        self.include, self.exclude = self._ranges(include), self._ranges(exclude)
        self.extended, self.names = extended, set(names)

    @staticmethod
    def _ranges(text):
        result = []
        for part in filter(None, text.split(",")):
            ends = part.split("-")
            low, high = int(ends[0], 0), int(ends[-1], 0)
            if len(ends) > 2 or not 0 <= low <= high <= 0x1FFFFFFF:
                raise ValueError("invalid ID range")
            result.append((low, high))
        return result

    def matches(self, frame, name=""):
        def hit(ranges):
            return any(a <= frame.identifier <= b for a, b in ranges)

        return (
            (not self.include or hit(self.include))
            and not hit(self.exclude)
            and (self.extended is None or bool(frame.flags & EXT) == self.extended)
            and (not self.names or name in self.names)
        )


class Decoder:
    def __init__(self, path):
        import cantools

        self.db = cantools.database.load_file(path, strict=True)
        self.messages = {(m.frame_id, m.is_extended_frame): m for m in self.db.messages}
        if any(m.is_container for m in self.db.messages):
            raise ValueError("container DBC messages are not supported")

    def decode(self, frame):
        msg = self.messages.get((frame.identifier, bool(frame.flags & EXT)))
        if msg is None:
            return "", {}, None
        try:
            if frame.flags & RTR:
                raise ValueError("RTR has no signal payload")
            values = msg.decode(
                frame.data,
                decode_choices=True,
                allow_truncated=False,
                allow_excess=False,
            )
            units = {s.name: s.unit for s in msg.signals}
            return (
                msg.name,
                {
                    k: {
                        "value": str(v) if not isinstance(v, (int, float)) else v,
                        "unit": units[k],
                    }
                    for k, v in values.items()
                },
                None,
            )
        except (ValueError, KeyError) as exc:
            return msg.name, {}, str(exc)
        except Exception as exc:
            return msg.name, {}, f"decode failed: {exc}"

    def encode(self, name, signals):
        from .protocol import Frame

        msg = self.db.get_message_by_name(name)
        if msg.autosar or msg.is_container:
            raise ValueError(
                "AUTOSAR/container command integrity semantics unsupported"
            )
        return Frame(
            msg.frame_id,
            msg.encode(signals, strict=True),
            (EXT if msg.is_extended_frame else 0) | (FD if msg.is_fd else 0),
        )


class Monitor:
    def __init__(self, limit=1000):
        self.trace = deque(maxlen=limit)
        self.latest = OrderedDict()
        self.limit = limit
        self.skipped = 0
        self.first = {}

    def add(self, frame, name="", signals=None):
        key = (frame.session, *frame.key)
        previous = self.latest.pop(key, None)
        first = self.first.setdefault(frame.session, frame.timestamp_us)
        if len(self.first) > 16:
            del self.first[next(iter(self.first))]
        row = dict(
            frame=frame,
            name=name,
            signals=signals or {},
            count=1 if previous is None else previous["count"] + 1,
            interval_us=None
            if previous is None
            else frame.timestamp_us - previous["frame"].timestamp_us,
            relative_us=frame.timestamp_us - first,
        )
        self.trace.append(row)
        self.latest[key] = row
        if len(self.latest) > self.limit:
            self.latest.popitem(last=False)
        return row


class AdapterQueue:
    """Nonblocking handoff. Adapter consumers cannot stall capture/recording."""

    def __init__(self, capacity=256):
        self.queue = Queue(capacity)
        self.discards = 0

    def publish(self, event):
        try:
            self.queue.put_nowait(event)
        except Full:
            self.discards += 1


class DiagnosticAdapter:
    """Implement consume(event); submit commands only through the owning Client."""

    def __init__(self, client, capacity=256):
        self.client, self.events = client, AdapterQueue(capacity)

    def send(self, frame, *, allow_tx=False):
        if not allow_tx:
            raise PermissionError("explicit active control required")
        return self.client.send_frame(frame)
