"""Read and write PNG tEXt/iTXt chunks without decoding pixels."""

from __future__ import annotations

import struct
import zlib

from cas import CasError
from cas.bounds import MAX_CHUNK, MAX_CHUNKS, MAX_NOTE_BYTES, MAX_PNG_BYTES, MAX_TITLE, MAX_URL_BYTES

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
TEXT_KEYS = frozenset({"Source", "Title", "Comment", "Creation Time", "URL"})


def _crc(chunk_type: bytes, data: bytes) -> int:
    return zlib.crc32(chunk_type + data) & 0xFFFFFFFF


def split_chunks(blob: bytes) -> list[tuple[bytes, bytes]]:
    if not blob.startswith(PNG_MAGIC):
        raise CasError("not a PNG")
    if len(blob) > MAX_PNG_BYTES:
        raise CasError("PNG exceeds size limit")
    pos = len(PNG_MAGIC)
    chunks: list[tuple[bytes, bytes]] = []
    while pos + 12 <= len(blob):
        if len(chunks) >= MAX_CHUNKS:
            raise CasError("too many PNG chunks")
        (length,) = struct.unpack(">I", blob[pos : pos + 4])
        if length > MAX_PNG_BYTES:
            raise CasError("PNG chunk too large")
        ctype = blob[pos + 4 : pos + 8]
        if len(ctype) != 4 or not all(65 <= b <= 122 for b in ctype):
            raise CasError("invalid PNG chunk type")
        data_start = pos + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(blob):
            raise CasError("truncated PNG")
        data = blob[data_start:data_end]
        (crc,) = struct.unpack(">I", blob[data_end:crc_end])
        if crc != _crc(ctype, data):
            raise CasError("PNG CRC mismatch")
        chunks.append((ctype, data))
        pos = crc_end
        if ctype == b"IEND":
            break
    else:
        raise CasError("PNG missing IEND")
    if pos != len(blob):
        # Trailing bytes after IEND: refuse rather than silently drop.
        raise CasError("PNG has trailing data")
    return chunks


def _pack_chunk(ctype: bytes, data: bytes) -> bytes:
    if len(data) > MAX_CHUNK and ctype in (b"tEXt", b"iTXt"):
        raise CasError("text chunk too large")
    return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", _crc(ctype, data))


def _itxt(keyword: str, text: str) -> bytes:
    if not keyword.isascii() or not keyword or len(keyword) > 79:
        raise CasError("bad PNG keyword")
    payload = text.encode("utf-8")
    if len(payload) > MAX_CHUNK - 16:
        payload = payload[: MAX_CHUNK - 16]
    # keyword\0 flag method language\0 translated\0 utf8
    data = keyword.encode("latin-1") + b"\x00\x00\x00\x00\x00" + payload
    return _pack_chunk(b"iTXt", data)


def _text_latin1(keyword: str, text: str) -> bytes:
    payload = text.encode("latin-1", "replace")
    data = keyword.encode("latin-1") + b"\x00" + payload
    return _pack_chunk(b"tEXt", data)


def parse_text(chunks: list[tuple[bytes, bytes]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for ctype, data in chunks:
        if ctype == b"tEXt":
            if b"\x00" not in data or len(data) > MAX_CHUNK:
                continue
            key, _, rest = data.partition(b"\x00")
            try:
                name = key.decode("latin-1")
                value = rest.decode("latin-1")
            except UnicodeDecodeError:
                continue
        elif ctype == b"iTXt":
            parsed = _parse_itxt(data)
            if parsed is None:
                continue
            name, value = parsed
        else:
            continue
        if name in TEXT_KEYS and name not in out:
            out[name] = value
    return out


def _parse_itxt(data: bytes) -> tuple[str, str] | None:
    if len(data) > MAX_CHUNK or b"\x00" not in data:
        return None
    key, _, rest = data.partition(b"\x00")
    if len(rest) < 4:
        return None
    flag, _method = rest[0], rest[1]
    if flag != 0:
        return None
    rest = rest[2:]
    _lang, _, rest = rest.partition(b"\x00")
    _translated, _, payload = rest.partition(b"\x00")
    try:
        return key.decode("latin-1"), payload.decode("utf-8")
    except UnicodeDecodeError:
        return None


def embed(blob: bytes, *, url: str | None, title: str, note: str, captured_at: str) -> bytes:
    chunks = split_chunks(blob)
    kept: list[tuple[bytes, bytes]] = []
    for ctype, data in chunks:
        if ctype in (b"tEXt", b"iTXt"):
            meta = parse_text([(ctype, data)])
            if meta and set(meta) & TEXT_KEYS:
                continue
        if ctype == b"IEND":
            continue
        kept.append((ctype, data))
    extras = b""
    if url:
        extras += _text_latin1("Source", url[:MAX_URL_BYTES])
        extras += _itxt("URL", url[:MAX_URL_BYTES])
    if title:
        extras += _itxt("Title", title[:MAX_TITLE])
    if note:
        extras += _itxt("Comment", note[:MAX_NOTE_BYTES])
    if captured_at:
        extras += _text_latin1("Creation Time", captured_at[:64])
    rebuilt = PNG_MAGIC
    for ctype, data in kept:
        rebuilt += _pack_chunk(ctype, data)
    rebuilt += extras
    rebuilt += _pack_chunk(b"IEND", b"")
    if len(rebuilt) > MAX_PNG_BYTES:
        raise CasError("PNG with metadata exceeds size limit")
    return rebuilt
