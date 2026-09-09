# /// zerodep
# version = "0.1.1"
# deps = []
# tier = "medium"
# category = "image"
# note = "Install/update via `zerodep add png`"
# ///
"""Zero-dependency PNG and BMP image codec with matrix compression API.

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

Encode and decode PNG (via stdlib zlib) and BMP images using only the
standard library.  Provides a shared ``Image`` data structure for format
conversion and a ``matrix_to_png`` / ``png_to_matrix`` API that exploits
PNG row filters for efficient 2-D numeric data compression.

Supported PNG features:
  - Color types: grayscale (0), RGB (2), grayscale+alpha (4), RGBA (6)
  - Bit depths: 8 and 16 per channel
  - All five adaptive row filters (None/Sub/Up/Average/Paeth)
  - tEXt ancillary chunks (read and write)

Supported BMP features:
  - 24-bit RGB and 32-bit RGBA, uncompressed
  - Bottom-up and top-down row order

Not supported (by design):
  - Adam7 interlacing, palette PNG (color type 3)
  - BMP RLE compression, BMP palette modes
"""

from __future__ import annotations

import dataclasses
import json
import os
import struct
import zlib
from typing import IO, Any

__all__ = [
    "ImageError",
    "DecodeError",
    "EncodeError",
    "Image",
    "decode_png",
    "encode_png",
    "decode_bmp",
    "encode_bmp",
    "matrix_to_png",
    "png_to_matrix",
    "convert",
]


# ============================================================================
# 1. Exceptions
# ============================================================================


class ImageError(Exception):
    """Base exception for image codec errors."""


class DecodeError(ImageError):
    """Raised when image decoding fails."""


class EncodeError(ImageError):
    """Raised when image encoding fails."""


# ============================================================================
# 2. Image dataclass and helpers
# ============================================================================

_MODE_BPP: dict[str, int] = {"L": 1, "LA": 2, "RGB": 3, "RGBA": 4}

_COLOR_TYPE_TO_MODE: dict[int, str] = {0: "L", 2: "RGB", 4: "LA", 6: "RGBA"}

_MODE_TO_COLOR_TYPE: dict[str, int] = {v: k for k, v in _COLOR_TYPE_TO_MODE.items()}


def _bytes_per_pixel(mode: str, bit_depth: int = 8) -> int:
    """Return bytes per pixel for the given mode and bit depth."""
    return _MODE_BPP[mode] * (bit_depth // 8)


@dataclasses.dataclass
class Image:
    """Decoded image pixel data.

    Attributes:
        width: Image width in pixels.
        height: Image height in pixels.
        data: Raw pixel bytes in row-major order.
        mode: Pixel format: ``'L'``, ``'LA'``, ``'RGB'``, or ``'RGBA'``.
        bit_depth: Bits per channel (8 or 16).
        metadata: Optional dict of ancillary text data (PNG tEXt chunks).
    """

    width: int
    height: int
    data: bytes
    mode: str
    bit_depth: int = 8
    metadata: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.mode not in _MODE_BPP:
            raise ValueError(f"unsupported mode {self.mode!r}")
        if self.bit_depth not in (8, 16):
            raise ValueError(f"unsupported bit_depth {self.bit_depth}")
        bpp = _bytes_per_pixel(self.mode, self.bit_depth)
        expected = self.width * self.height * bpp
        if len(self.data) != expected:
            raise ValueError(
                f"data length {len(self.data)} does not match "
                f"{self.width}x{self.height} {self.mode} {self.bit_depth}-bit "
                f"(expected {expected})"
            )


# ============================================================================
# 3. I/O helpers
# ============================================================================


def _read_source(source: str | os.PathLike[str] | IO[bytes] | bytes) -> bytes:
    """Read raw bytes from a file path, file object, or bytes."""
    if isinstance(source, (str, os.PathLike)):
        with open(source, "rb") as f:
            return f.read()
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source)
    return source.read()


def _write_dest(
    dest: str | os.PathLike[str] | IO[bytes] | None, data: bytes
) -> bytes | None:
    """Write *data* to *dest*.  Return bytes when *dest* is ``None``."""
    if dest is None:
        return data
    if isinstance(dest, (str, os.PathLike)):
        with open(dest, "wb") as f:
            f.write(data)
        return None
    dest.write(data)
    return None


# ============================================================================
# 4. PNG chunk primitives
# ============================================================================

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _read_chunks(raw: bytes) -> list[tuple[bytes, bytes]]:
    """Parse all PNG chunks from *raw* bytes (after signature validation).

    Returns:
        List of ``(chunk_type, chunk_data)`` tuples.
    """
    if not raw.startswith(_PNG_SIGNATURE):
        raise DecodeError("not a PNG file (bad signature)")
    chunks: list[tuple[bytes, bytes]] = []
    pos = 8
    while pos < len(raw):
        if pos + 8 > len(raw):
            raise DecodeError("truncated chunk header")
        length = struct.unpack(">I", raw[pos : pos + 4])[0]
        ctype = raw[pos + 4 : pos + 8]
        if pos + 12 + length > len(raw):
            raise DecodeError(f"truncated {ctype!r} chunk data")
        cdata = raw[pos + 8 : pos + 8 + length]
        crc_stored = struct.unpack(">I", raw[pos + 8 + length : pos + 12 + length])[0]
        crc_calc = zlib.crc32(ctype + cdata) & 0xFFFFFFFF
        if crc_stored != crc_calc:
            raise DecodeError(f"CRC mismatch in {ctype!r} chunk")
        chunks.append((ctype, cdata))
        pos += 12 + length
    return chunks


def _write_chunk(ctype: bytes, cdata: bytes) -> bytes:
    """Build a single PNG chunk (length + type + data + CRC)."""
    crc = zlib.crc32(ctype + cdata) & 0xFFFFFFFF
    return struct.pack(">I", len(cdata)) + ctype + cdata + struct.pack(">I", crc)


# ============================================================================
# 5. PNG row filters
# ============================================================================


def _paeth(a: int, b: int, c: int) -> int:
    """Paeth predictor (PNG spec)."""
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


# ---- Decode (unfilter) -----------------------------------------------------


def _unfilter_row(ftype: int, raw: bytes, prev: bytes | None, bpp: int) -> bytearray:
    """Reverse one row filter.  *prev* is the previous unfiltered row."""
    n = len(raw)
    if ftype == 0:  # None
        return bytearray(raw)
    prv = prev or b"\x00" * n
    if ftype == 2:  # Up — no sequential dependency
        return bytearray([(r + p) & 0xFF for r, p in zip(raw, prv)])
    out = bytearray(n)
    if ftype == 1:  # Sub
        out[:bpp] = raw[:bpp]
        for i in range(bpp, n):
            out[i] = (raw[i] + out[i - bpp]) & 0xFF
    elif ftype == 3:  # Average
        for i in range(n):
            left = out[i - bpp] if i >= bpp else 0
            out[i] = (raw[i] + ((left + prv[i]) >> 1)) & 0xFF
    elif ftype == 4:  # Paeth
        _pa = _paeth
        for i in range(n):
            left = out[i - bpp] if i >= bpp else 0
            up = prv[i]
            upleft = prv[i - bpp] if i >= bpp else 0
            out[i] = (raw[i] + _pa(left, up, upleft)) & 0xFF
    else:
        raise DecodeError(f"unknown filter type {ftype}")
    return out


# ---- Encode (filter) -------------------------------------------------------


def _filter_row(ftype: int, raw: bytes, prev: bytes, bpp: int) -> bytes:
    """Apply one row filter for encoding."""
    n = len(raw)
    if ftype == 0:  # None
        return bytes(raw)
    if ftype == 2:  # Up — no sequential dependency
        return bytes([(r - p) & 0xFF for r, p in zip(raw, prev)])
    out = bytearray(n)
    if ftype == 1:  # Sub
        out[:bpp] = raw[:bpp]
        for i in range(bpp, n):
            out[i] = (raw[i] - raw[i - bpp]) & 0xFF
    elif ftype == 3:  # Average
        for i in range(n):
            left = raw[i - bpp] if i >= bpp else 0
            out[i] = (raw[i] - ((left + prev[i]) >> 1)) & 0xFF
    elif ftype == 4:  # Paeth
        _pa = _paeth
        for i in range(n):
            left = raw[i - bpp] if i >= bpp else 0
            up = prev[i]
            upleft = prev[i - bpp] if i >= bpp else 0
            out[i] = (raw[i] - _pa(left, up, upleft)) & 0xFF
    return bytes(out)


def _select_filter(raw: bytes, prev: bytes, bpp: int) -> tuple[int, bytes]:
    """Try all five filters and return the one with the smallest sum of
    absolute values (minimum-sum heuristic from the PNG specification)."""
    best_type = 0
    best_data = _filter_row(0, raw, prev, bpp)
    best_sum = sum(best_data)
    for ftype in range(1, 5):
        filtered = _filter_row(ftype, raw, prev, bpp)
        s = sum((b if b < 128 else 256 - b) for b in filtered)
        if s < best_sum:
            best_sum = s
            best_type = ftype
            best_data = filtered
    return best_type, best_data


# ============================================================================
# 6. PNG decode
# ============================================================================


def decode_png(source: str | os.PathLike[str] | IO[bytes] | bytes) -> Image:
    """Decode a PNG image into an :class:`Image`.

    Args:
        source: File path, file object, or raw PNG bytes.

    Returns:
        Decoded image.

    Raises:
        DecodeError: If the data is not valid PNG or uses unsupported features.
    """
    raw = _read_source(source)
    chunks = _read_chunks(raw)

    # -- IHDR -----------------------------------------------------------------
    if not chunks or chunks[0][0] != b"IHDR":
        raise DecodeError("missing IHDR chunk")
    ihdr = chunks[0][1]
    if len(ihdr) != 13:
        raise DecodeError("bad IHDR length")
    width, height = struct.unpack(">II", ihdr[:8])
    bit_depth = ihdr[8]
    color_type = ihdr[9]
    compression = ihdr[10]
    filter_method = ihdr[11]
    interlace = ihdr[12]

    if width == 0 or height == 0:
        raise DecodeError("zero-dimension image")
    if compression != 0:
        raise DecodeError(f"unsupported compression method {compression}")
    if filter_method != 0:
        raise DecodeError(f"unsupported filter method {filter_method}")
    if interlace != 0:
        raise DecodeError("interlaced PNG is not supported")
    if color_type not in _COLOR_TYPE_TO_MODE:
        raise DecodeError(f"unsupported color type {color_type}")
    if bit_depth not in (8, 16):
        raise DecodeError(f"unsupported bit depth {bit_depth}")

    mode = _COLOR_TYPE_TO_MODE[color_type]
    bpp = _bytes_per_pixel(mode, bit_depth)
    row_bytes = width * bpp

    # -- Collect IDAT and tEXt ------------------------------------------------
    idat_parts: list[bytes] = []
    metadata: dict[str, str] = {}
    for ctype, cdata in chunks:
        if ctype == b"IDAT":
            idat_parts.append(cdata)
        elif ctype == b"tEXt":
            sep = cdata.find(b"\x00")
            if sep != -1:
                key = cdata[:sep].decode("latin-1")
                val = cdata[sep + 1 :].decode("latin-1")
                metadata[key] = val

    if not idat_parts:
        raise DecodeError("no IDAT chunks found")

    # -- Decompress and unfilter ----------------------------------------------
    try:
        decompressed = zlib.decompress(b"".join(idat_parts))
    except zlib.error as exc:
        raise DecodeError(f"zlib decompression failed: {exc}") from exc

    expected_len = height * (1 + row_bytes)  # 1 filter byte per row
    if len(decompressed) != expected_len:
        raise DecodeError(
            f"decompressed size {len(decompressed)} != expected {expected_len}"
        )

    pixels = bytearray(height * row_bytes)
    prev_row: bytes | None = None
    stride = 1 + row_bytes
    for y in range(height):
        offset = y * stride
        ftype = decompressed[offset]
        row_data = decompressed[offset + 1 : offset + 1 + row_bytes]
        unfiltered = _unfilter_row(ftype, row_data, prev_row, bpp)
        pixels[y * row_bytes : (y + 1) * row_bytes] = unfiltered
        prev_row = bytes(unfiltered)

    return Image(
        width=width,
        height=height,
        data=bytes(pixels),
        mode=mode,
        bit_depth=bit_depth,
        metadata=metadata or None,
    )


# ============================================================================
# 7. PNG encode
# ============================================================================


def encode_png(
    image: Image,
    dest: str | os.PathLike[str] | IO[bytes] | None = None,
    *,
    filter_strategy: str = "auto",
    compression_level: int = 6,
) -> bytes | None:
    """Encode an :class:`Image` as PNG.

    Args:
        image: Image to encode.
        dest: File path, file object, or ``None`` to return bytes.
        filter_strategy: Row filter strategy — ``'auto'`` (minimum-sum
            heuristic), ``'none'``, ``'sub'``, ``'up'``, ``'avg'``, or
            ``'paeth'``.
        compression_level: zlib compression level (0–9).

    Returns:
        PNG bytes when *dest* is ``None``, otherwise ``None``.
    """
    if image.mode not in _MODE_TO_COLOR_TYPE:
        raise EncodeError(f"unsupported mode {image.mode!r}")

    color_type = _MODE_TO_COLOR_TYPE[image.mode]
    bpp = _bytes_per_pixel(image.mode, image.bit_depth)
    row_bytes = image.width * bpp

    fixed_filter: int | None = {
        "none": 0,
        "sub": 1,
        "up": 2,
        "avg": 3,
        "paeth": 4,
    }.get(filter_strategy)

    # -- Build filtered scanlines ---------------------------------------------
    total_filtered = image.height * (1 + row_bytes)
    filtered = bytearray(total_filtered)
    prev_row = b"\x00" * row_bytes
    filt_stride = 1 + row_bytes
    for y in range(image.height):
        row = image.data[y * row_bytes : (y + 1) * row_bytes]
        filt_offset = y * filt_stride
        if filter_strategy == "auto":
            ftype, fdata = _select_filter(row, prev_row, bpp)
        elif fixed_filter is not None:
            ftype = fixed_filter
            fdata = _filter_row(ftype, row, prev_row, bpp)
        else:
            raise EncodeError(f"unknown filter_strategy {filter_strategy!r}")
        filtered[filt_offset] = ftype
        filtered[filt_offset + 1 : filt_offset + 1 + row_bytes] = fdata
        prev_row = row

    compressed = zlib.compress(bytes(filtered), compression_level)

    # -- Assemble chunks ------------------------------------------------------
    ihdr_data = struct.pack(
        ">IIBBBBB",
        image.width,
        image.height,
        image.bit_depth,
        color_type,
        0,  # compression
        0,  # filter method
        0,  # interlace
    )

    parts = [_PNG_SIGNATURE, _write_chunk(b"IHDR", ihdr_data)]

    # tEXt chunks
    if image.metadata:
        for key, val in image.metadata.items():
            tdata = key.encode("latin-1") + b"\x00" + val.encode("latin-1")
            parts.append(_write_chunk(b"tEXt", tdata))

    parts.append(_write_chunk(b"IDAT", compressed))
    parts.append(_write_chunk(b"IEND", b""))

    return _write_dest(dest, b"".join(parts))


# ============================================================================
# 8. BMP decode
# ============================================================================

_BMP_SIGNATURE = b"BM"


def decode_bmp(source: str | os.PathLike[str] | IO[bytes] | bytes) -> Image:
    """Decode a BMP image into an :class:`Image`.

    Args:
        source: File path, file object, or raw BMP bytes.

    Returns:
        Decoded image.

    Raises:
        DecodeError: If the data is not valid BMP or uses unsupported features.
    """
    raw = _read_source(source)

    if len(raw) < 54:
        raise DecodeError("file too small for BMP")
    if raw[:2] != _BMP_SIGNATURE:
        raise DecodeError("not a BMP file (bad signature)")

    # File header (14 bytes)
    data_offset = struct.unpack("<I", raw[10:14])[0]

    # DIB header (BITMAPINFOHEADER, 40 bytes minimum)
    dib_size = struct.unpack("<I", raw[14:18])[0]
    if dib_size < 40:
        raise DecodeError(f"unsupported DIB header size {dib_size}")

    width = struct.unpack("<i", raw[18:22])[0]
    height_raw = struct.unpack("<i", raw[22:26])[0]
    bits_per_pixel = struct.unpack("<H", raw[28:30])[0]
    compression = struct.unpack("<I", raw[30:34])[0]

    if compression != 0:
        raise DecodeError(f"unsupported BMP compression {compression}")
    if bits_per_pixel not in (24, 32):
        raise DecodeError(f"unsupported BMP bit depth {bits_per_pixel}")

    top_down = height_raw < 0
    height = abs(height_raw)

    if width <= 0 or height == 0:
        raise DecodeError("invalid BMP dimensions")

    bmp_bpp = bits_per_pixel // 8
    row_data_bytes = width * bmp_bpp
    row_stride = (row_data_bytes + 3) & ~3  # pad to 4-byte boundary

    mode = "RGBA" if bits_per_pixel == 32 else "RGB"
    out_bpp = _MODE_BPP[mode]

    pixels = bytearray(width * height * out_bpp)
    for y in range(height):
        # BMP default is bottom-up; top-down if height was negative
        src_y = y if top_down else (height - 1 - y)
        src_offset = data_offset + src_y * row_stride
        if src_offset + row_data_bytes > len(raw):
            raise DecodeError("truncated BMP pixel data")

        src_row = raw[src_offset : src_offset + row_data_bytes]
        dst_offset = y * width * out_bpp
        dst_row = bytearray(width * out_bpp)
        if bmp_bpp == 3:
            # BGR -> RGB via slice assignment (C-level ops)
            dst_row[0::3] = src_row[2::3]  # R
            dst_row[1::3] = src_row[1::3]  # G
            dst_row[2::3] = src_row[0::3]  # B
        else:
            # BGRA -> RGBA via slice assignment
            dst_row[0::4] = src_row[2::4]  # R
            dst_row[1::4] = src_row[1::4]  # G
            dst_row[2::4] = src_row[0::4]  # B
            dst_row[3::4] = src_row[3::4]  # A
        pixels[dst_offset : dst_offset + width * out_bpp] = dst_row

    return Image(width=width, height=height, data=bytes(pixels), mode=mode)


# ============================================================================
# 9. BMP encode
# ============================================================================


def encode_bmp(
    image: Image,
    dest: str | os.PathLike[str] | IO[bytes] | None = None,
) -> bytes | None:
    """Encode an :class:`Image` as BMP.

    Args:
        image: Image to encode (must be ``'RGB'`` or ``'RGBA'``).
        dest: File path, file object, or ``None`` to return bytes.

    Returns:
        BMP bytes when *dest* is ``None``, otherwise ``None``.
    """
    if image.mode not in ("RGB", "RGBA"):
        raise EncodeError(f"BMP encode requires RGB or RGBA mode, got {image.mode!r}")
    if image.bit_depth != 8:
        raise EncodeError("BMP encode only supports 8-bit images")

    bmp_bpp = 4 if image.mode == "RGBA" else 3
    src_bpp = _MODE_BPP[image.mode]
    bits_per_pixel = bmp_bpp * 8
    row_data_bytes = image.width * bmp_bpp
    row_stride = (row_data_bytes + 3) & ~3
    padding = row_stride - row_data_bytes

    dib_size = 40
    data_offset = 14 + dib_size
    file_size = data_offset + row_stride * image.height

    buf = bytearray()

    # File header (14 bytes)
    buf.extend(b"BM")
    buf.extend(struct.pack("<I", file_size))
    buf.extend(b"\x00\x00\x00\x00")  # reserved
    buf.extend(struct.pack("<I", data_offset))

    # DIB header (40 bytes)
    buf.extend(struct.pack("<I", dib_size))
    buf.extend(struct.pack("<i", image.width))
    buf.extend(struct.pack("<i", image.height))  # positive = bottom-up
    buf.extend(struct.pack("<H", 1))  # planes
    buf.extend(struct.pack("<H", bits_per_pixel))
    buf.extend(struct.pack("<I", 0))  # compression = none
    buf.extend(struct.pack("<I", row_stride * image.height))  # image size
    buf.extend(b"\x00" * 16)  # resolution + palette counts

    # Pixel data (bottom-up)
    pad_bytes = b"\x00" * padding
    for y in range(image.height - 1, -1, -1):
        row_offset = y * image.width * src_bpp
        src_row = image.data[row_offset : row_offset + image.width * src_bpp]
        bmp_row = bytearray(row_data_bytes)
        if bmp_bpp == 3:
            # RGB -> BGR via slice assignment (C-level ops)
            bmp_row[0::3] = src_row[2::3]  # B
            bmp_row[1::3] = src_row[1::3]  # G
            bmp_row[2::3] = src_row[0::3]  # R
        else:
            # RGBA -> BGRA via slice assignment
            bmp_row[0::4] = src_row[2::4]  # B
            bmp_row[1::4] = src_row[1::4]  # G
            bmp_row[2::4] = src_row[0::4]  # R
            bmp_row[3::4] = src_row[3::4]  # A
        buf.extend(bmp_row)
        buf.extend(pad_bytes)

    return _write_dest(dest, bytes(buf))


# ============================================================================
# 10. Mode conversion
# ============================================================================


def convert(image: Image, mode: str) -> Image:
    """Convert an :class:`Image` to a different pixel mode.

    Args:
        image: Source image.
        mode: Target mode (``'L'``, ``'LA'``, ``'RGB'``, ``'RGBA'``).

    Returns:
        New image in the target mode.

    Raises:
        ValueError: If the conversion is not supported.
    """
    if mode not in _MODE_BPP:
        raise ValueError(f"unsupported target mode {mode!r}")
    if image.mode == mode:
        return dataclasses.replace(image)
    if image.bit_depth != 8:
        raise ValueError("convert() only supports 8-bit images")

    src = image.data
    w, h = image.width, image.height
    npx = w * h
    dst_bpp = _MODE_BPP[mode]
    out = bytearray(npx * dst_bpp)

    key = (image.mode, mode)

    if key == ("L", "RGB"):
        out[0::3] = src
        out[1::3] = src
        out[2::3] = src
    elif key == ("L", "RGBA"):
        out[0::4] = src
        out[1::4] = src
        out[2::4] = src
        out[3::4] = b"\xff" * npx
    elif key == ("L", "LA"):
        out[0::2] = src
        out[1::2] = b"\xff" * npx
    elif key == ("LA", "L"):
        out[:] = src[0::2]
    elif key == ("LA", "RGBA"):
        lum = src[0::2]
        out[0::4] = lum
        out[1::4] = lum
        out[2::4] = lum
        out[3::4] = src[1::2]
    elif key == ("LA", "RGB"):
        lum = src[0::2]
        out[0::3] = lum
        out[1::3] = lum
        out[2::3] = lum
    elif key == ("RGB", "RGBA"):
        out[0::4] = src[0::3]
        out[1::4] = src[1::3]
        out[2::4] = src[2::3]
        out[3::4] = b"\xff" * npx
    elif key == ("RGB", "L"):
        for i in range(npx):
            si = i * 3
            out[i] = (
                src[si] * 299 + src[si + 1] * 587 + src[si + 2] * 114 + 500
            ) // 1000
    elif key == ("RGB", "LA"):
        for i in range(npx):
            si = i * 3
            o = i * 2
            out[o] = (
                src[si] * 299 + src[si + 1] * 587 + src[si + 2] * 114 + 500
            ) // 1000
            out[o + 1] = 255
    elif key == ("RGBA", "RGB"):
        out[0::3] = src[0::4]
        out[1::3] = src[1::4]
        out[2::3] = src[2::4]
    elif key == ("RGBA", "L"):
        for i in range(npx):
            si = i * 4
            out[i] = (
                src[si] * 299 + src[si + 1] * 587 + src[si + 2] * 114 + 500
            ) // 1000
    elif key == ("RGBA", "LA"):
        for i in range(npx):
            si = i * 4
            o = i * 2
            out[o] = (
                src[si] * 299 + src[si + 1] * 587 + src[si + 2] * 114 + 500
            ) // 1000
            out[o + 1] = src[si + 3]
    else:
        raise ValueError(f"unsupported conversion {image.mode!r} -> {mode!r}")

    return Image(
        width=w,
        height=h,
        data=bytes(out),
        mode=mode,
        bit_depth=8,
        metadata=image.metadata,
    )


# ============================================================================
# 11. Matrix API
# ============================================================================

_MATRIX_TEXT_KEY = "zerodep:matrix"


def matrix_to_png(
    matrix: list[list[int | float]] | list[list[Any]],
    dest: str | os.PathLike[str] | IO[bytes] | None = None,
    *,
    bit_depth: int = 8,
    filter_strategy: str = "auto",
    compression_level: int = 6,
) -> bytes | None:
    """Encode a 2-D numeric matrix as a grayscale PNG.

    Integer values in ``[0, 2^bit_depth - 1]`` are stored directly.
    Float values (or out-of-range integers) are linearly mapped to
    the full pixel range; the mapping parameters are stored in a PNG
    ``tEXt`` chunk so :func:`png_to_matrix` can reconstruct them.

    Args:
        matrix: Rows of numeric values (all rows must have equal length).
        dest: File path, file object, or ``None`` to return bytes.
        bit_depth: 8 or 16 bits per sample.
        filter_strategy: PNG row filter strategy.
        compression_level: zlib compression level (0–9).

    Returns:
        PNG bytes when *dest* is ``None``, otherwise ``None``.
    """
    if not matrix or not matrix[0]:
        raise EncodeError("matrix must be non-empty")

    rows = len(matrix)
    cols = len(matrix[0])
    max_val = (1 << bit_depth) - 1

    # Determine dtype and mapping
    all_int = all(isinstance(v, int) for row in matrix for v in row)
    vmin: float = min(min(row) for row in matrix)
    vmax: float = max(max(row) for row in matrix)

    need_mapping = not all_int or vmin < 0 or vmax > max_val
    dtype = "float64" if need_mapping else (f"uint{bit_depth}")

    if need_mapping and vmin == vmax:
        scale = 0.0
    elif need_mapping:
        scale = max_val / (vmax - vmin)
    else:
        scale = 1.0

    # Build pixel data
    if bit_depth == 8:
        pixels = bytearray(rows * cols)
        idx = 0
        if need_mapping:
            for row in matrix:
                for v in row:
                    pixels[idx] = max(0, min(max_val, round((v - vmin) * scale)))
                    idx += 1
        else:
            for row in matrix:
                for v in row:
                    pixels[idx] = int(v)
                    idx += 1
    else:  # 16-bit
        pixels = bytearray(rows * cols * 2)
        idx = 0
        if need_mapping:
            for row in matrix:
                for v in row:
                    pv = max(0, min(max_val, round((v - vmin) * scale)))
                    struct.pack_into(">H", pixels, idx, pv)
                    idx += 2
        else:
            for row in matrix:
                for v in row:
                    struct.pack_into(">H", pixels, idx, int(v))
                    idx += 2

    metadata: dict[str, str] = {}
    meta_info: dict[str, Any] = {
        "dtype": dtype,
        "rows": rows,
        "cols": cols,
    }
    if need_mapping:
        meta_info["min"] = vmin
        meta_info["max"] = vmax
    metadata[_MATRIX_TEXT_KEY] = json.dumps(meta_info, separators=(",", ":"))

    img = Image(
        width=cols,
        height=rows,
        data=bytes(pixels),
        mode="L",
        bit_depth=bit_depth,
        metadata=metadata,
    )
    return encode_png(
        img,
        dest,
        filter_strategy=filter_strategy,
        compression_level=compression_level,
    )


def png_to_matrix(
    source: str | os.PathLike[str] | IO[bytes] | bytes,
) -> list[list[int]] | list[list[float]]:
    """Decode a grayscale PNG into a 2-D numeric matrix.

    If the PNG contains ``zerodep:matrix`` metadata (written by
    :func:`matrix_to_png`), float values are reconstructed from the
    stored scale and offset.  Otherwise raw pixel values are returned
    as integers.

    Args:
        source: File path, file object, or raw PNG bytes.

    Returns:
        2-D list of numeric values.
    """
    img = decode_png(source)

    # Convert to grayscale if needed
    if img.mode != "L":
        img = convert(img, "L")

    max_val = (1 << img.bit_depth) - 1

    # Parse metadata
    meta_info: dict[str, Any] | None = None
    if img.metadata and _MATRIX_TEXT_KEY in img.metadata:
        try:
            meta_info = json.loads(img.metadata[_MATRIX_TEXT_KEY])
        except (json.JSONDecodeError, KeyError):
            meta_info = None

    need_mapping = meta_info is not None and meta_info.get("dtype") == "float64"

    if img.bit_depth == 16:
        # Unpack 16-bit values
        raw_values: list[int] = []
        for i in range(0, len(img.data), 2):
            raw_values.append(struct.unpack(">H", img.data[i : i + 2])[0])
    else:
        raw_values = list(img.data)

    rows = img.height
    cols = img.width

    if need_mapping:
        assert meta_info is not None
        vmin = meta_info["min"]
        vmax = meta_info["max"]
        if vmin == vmax:
            scale_inv = 0.0
        else:
            scale_inv = (vmax - vmin) / max_val
        result_float: list[list[float]] = []
        for y in range(rows):
            row: list[float] = []
            for x in range(cols):
                pv = raw_values[y * cols + x]
                row.append(vmin + pv * scale_inv)
            result_float.append(row)
        return result_float

    result_int: list[list[int]] = []
    for y in range(rows):
        result_int.append(raw_values[y * cols : (y + 1) * cols])
    return result_int
