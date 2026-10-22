"""Independent, read-only offline ADHDSTATE1 and route registry inspection.

The fixture reads its own accepted files; it never imports generated modules,
opens DETS, rewrites accepted state, or executes decoded terms.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import struct


def canonical(value):
    # All schema field names are ASCII and every numeric field is an integer;
    # therefore this is also RFC8785 JCS for these closed metadata objects.
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Atom(str):
    """Keep ETF atoms distinct from original UTF8 JSON string values."""


def exact(value):
    """Type-sensitive evidence equality, including integer/float and -0.0."""
    if isinstance(value, dict):
        return ("map", frozenset((exact(key), exact(item)) for key, item in value.items()))
    if isinstance(value, (tuple, list)):
        return (type(value).__name__, tuple(exact(item) for item in value))
    if isinstance(value, float):
        return ("float", struct.pack(">d", value))
    return (type(value).__name__, value)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key in accepted fixture metadata")
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


class Terms:
    """Bounded safe ETF data reader, intentionally without compression/executables."""
    def __init__(self, body):
        self.body, self.offset, self.nodes = body, 0, 0

    def take(self, count):
        if count < 0 or self.offset + count > len(self.body):
            raise ValueError("Truncated ETF data")
        value = self.body[self.offset:self.offset + count]
        self.offset += count
        return value

    def number(self, count):
        return int.from_bytes(self.take(count), "big")

    def term(self, depth=0):
        self.nodes += 1
        if depth > 256 or self.nodes > 1000000:
            raise ValueError("ETF fixture bounds exceeded")
        tag = self.number(1)
        if tag == 97:
            return self.number(1)
        if tag == 98:
            return int.from_bytes(self.take(4), "big", signed=True)
        if tag == 70:
            return struct.unpack(">d", self.take(8))[0]
        if tag in (100, 115, 118, 119):
            value = self.take(self.number(1 if tag in (115, 119) else 2)).decode("utf-8" if tag >= 118 else "latin-1")
            return {"nil": None, "true": True, "false": False}.get(value, Atom(value))
        if tag in (104, 105):
            return tuple(self.term(depth + 1) for _ in range(self.number(1 if tag == 104 else 4)))
        if tag == 106:
            return []
        if tag == 107:
            return list(self.take(self.number(2)))
        if tag == 108:
            items = [self.term(depth + 1) for _ in range(self.number(4))]
            if self.term(depth + 1) != []:
                raise ValueError("Improper ETF list in accepted fixture")
            return items
        if tag == 109:
            raw = self.take(self.number(4))
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError:
                return raw
        if tag in (110, 111):
            count = self.number(1 if tag == 110 else 4)
            sign = self.number(1)
            if sign not in (0, 1):
                raise ValueError("Invalid ETF sign")
            return int.from_bytes(self.take(count), "little") * (-1 if sign else 1)
        if tag == 116:
            value = {}
            for _ in range(self.number(4)):
                key, item = self.term(depth + 1), self.term(depth + 1)
                if key in value:
                    raise ValueError("Duplicate ETF map key")
                value[key] = item
            return value
        raise ValueError("Unsupported or unsafe ETF tag " + str(tag))


def snapshot(path):
    raw = Path(path).read_bytes()
    if len(raw) > 67108864 or not raw.startswith(b"ADHDSTATE\x01"):
        raise ValueError("Unexpected authoritative snapshot frame")
    expected, body = raw[10:42], raw[42:]
    if hashlib.sha256(body).digest() != expected or not body.startswith(b"\x83"):
        raise ValueError("Snapshot frame checksum/version mismatch")
    reader = Terms(body[1:])
    value = reader.term()
    if reader.offset != len(reader.body) or not isinstance(value, dict):
        raise ValueError("Trailing or non-map snapshot state")
    return value


def registry(config_file):
    value = read_json(str(config_file) + ".stores")
    expected = value.pop("integrity_sha256")
    if digest(canonical(value)) != expected:
        raise ValueError("Storage registry integrity mismatch")
    if value["schema"] != 1 or value["config_file"] != str(Path(config_file).resolve()):
        raise ValueError("Storage registry schema/config binding mismatch")
    value["integrity_sha256"] = expected
    return value


def route(config_file, project_id):
    value = registry(config_file)
    projects = value["projects"]
    entry = projects[project_id] if isinstance(projects, dict) else next(p for p in projects if p["project_id"] == project_id)
    assert entry["project_id"] == project_id and entry["server_id"] == value["server_id"]
    anchor = Path(entry["storage_anchor"])
    assert anchor.is_absolute() and not anchor.is_symlink()
    return entry, anchor
