import cantools
from .protocol import Frame, EXT, FD, RTR


class Decoder:
    def __init__(self, path):
        self.db = cantools.database.load_file(path, strict=True)
        self.messages = {(m.frame_id, m.is_extended_frame): m for m in self.db.messages}
        self.warnings = []
        for m in self.db.messages:
            if m.is_container or m.autosar:
                self.warnings.append(
                    f"{m.name}: container/AUTOSAR integrity semantics are unsupported"
                )

    def decode(self, frame):
        message = self.messages.get((frame.identifier, bool(frame.flags & EXT)))
        if message is None:
            return {"name": None, "signals": {}, "error": "no definition"}
        try:
            if frame.flags & RTR or message.is_container:
                raise ValueError("RTR/container decoding unsupported")
            signals = message.decode(
                frame.data,
                decode_choices=True,
                allow_truncated=False,
                allow_excess=False,
            )
            return {
                "name": message.name,
                "signals": {
                    k: v if isinstance(v, (int, float, str)) else str(v)
                    for k, v in signals.items()
                },
                "units": {s.name: s.unit for s in message.signals},
                "error": None,
            }
        except (ValueError, cantools.database.errors.DecodeError) as exc:
            return {"name": message.name, "signals": {}, "error": str(exc)}

    def encode(self, name, signals, *, brs=False):
        m = self.db.get_message_by_name(name)
        if m.is_container or m.autosar:
            raise ValueError("container/AUTOSAR command construction unsupported")
        return Frame(
            m.frame_id,
            m.encode(signals, strict=True),
            (EXT if m.is_extended_frame else 0)
            | (FD if m.is_fd else 0)
            | (4 if brs else 0),
        )
