# /// zerodep
# version = "0.3.3"
# deps = ["png"]
# tier = "simple"
# category = "image"
# note = "Install/update via: https://zerodep.readthedocs.io/en/latest/guide/cli/"
# ///

"""QR Code generator library (Python).

Part of zerodep: https://github.com/Oaklight/zerodep
Copyright (c) 2026 Peng Ding. MIT License.

Originally derived from Project Nayuki's QR Code generator (MIT License),
substantially refactored for the zerodep project:
    Copyright (c) Project Nayuki
    https://www.nayuki.io/page/qr-code-generator-library
"""

from __future__ import annotations

import itertools
import os
import re
import sys
from collections.abc import Callable, Sequence
from typing import Union

# ---- Precomputed GF(2^8) tables for Reed-Solomon ----
# Primitive polynomial: x^8 + x^4 + x^3 + x^2 + 1 (0x11D)

_GF_EXP: list[int] = [0] * 512  # Anti-log table: _GF_EXP[i] = 2^i mod 0x11D
_GF_LOG: list[int] = [0] * 256  # Log table: _GF_LOG[_GF_EXP[i]] = i


def _init_gf_tables() -> None:
    """Initialize GF(2^8) exp/log lookup tables at module load time."""
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_LOG[x] = i
        x = (x << 1) ^ ((x >> 7) * 0x11D)
    # Extend exp table for easy modular access: EXP[i+j] without % 255
    for i in range(255, 512):
        _GF_EXP[i] = _GF_EXP[i - 255]


_init_gf_tables()

# Precomputed 256x256 GF multiplication table (64 KB, much faster than function calls)
_GF_MUL: list[list[int]] = [[0] * 256 for _ in range(256)]


def _init_gf_mul_table() -> None:
    """Precompute full GF(2^8) multiplication table."""
    for x in range(1, 256):
        lx = _GF_LOG[x]
        row = _GF_MUL[x]
        for y in range(1, 256):
            row[y] = _GF_EXP[lx + _GF_LOG[y]]


_init_gf_mul_table()

__all__ = [
    "QrCode",
    "QrSegment",
    "DataTooLongError",
    "print_qr_terminal",
    "qr_to_svg",
    "qr_to_png",
]


# ---- Mask grid precomputation ----


def _build_mask_grids(isfunction: list[bytearray], size: int) -> list[list[bytearray]]:
    """Precompute mask XOR grids for all 8 mask patterns.

    Each grid stores 1 for data cells where the mask condition is true and
    0 elsewhere (including function cells). This allows mask application by
    simple XOR without per-pixel arithmetic or isfunction checks.

    Args:
        isfunction: Grid marking function modules (not subject to masking).
        size: Width/height of the QR code.

    Returns:
        A list of 8 grids (list of bytearray), one per mask pattern.
    """
    grids: list[list[bytearray]] = [
        [bytearray(size) for _ in range(size)] for _ in range(8)
    ]
    for y in range(size):
        isfunc_y = isfunction[y]
        grows = [grids[m][y] for m in range(8)]
        for x in range(size):
            if not isfunc_y[x]:
                _fill_mask_pixel(grows, x, y)
    return grids


def _fill_mask_pixel(grows: list[bytearray], x: int, y: int) -> None:
    """Compute and store all 8 mask pattern values for one pixel.

    Args:
        grows: List of 8 bytearray rows (one per mask pattern) to fill.
        x: Horizontal coordinate.
        y: Vertical coordinate.
    """
    xy = x * y
    grows[0][x] = 1 if (x + y) % 2 == 0 else 0
    grows[1][x] = 1 if y % 2 == 0 else 0
    grows[2][x] = 1 if x % 3 == 0 else 0
    grows[3][x] = 1 if (x + y) % 3 == 0 else 0
    grows[4][x] = 1 if (x // 3 + y // 2) % 2 == 0 else 0
    grows[5][x] = 1 if xy % 2 + xy % 3 == 0 else 0
    grows[6][x] = 1 if (xy % 2 + xy % 3) % 2 == 0 else 0
    grows[7][x] = 1 if ((x + y) % 2 + xy % 3) % 2 == 0 else 0


def _apply_precomputed_mask(
    modules: list[bytearray], mask_grid: list[bytearray], size: int
) -> None:
    """Apply a precomputed mask grid to modules via bulk row XOR.

    Uses int.from_bytes for efficient whole-row XOR instead of
    element-by-element iteration.

    Args:
        modules: The QR code module grid to mask in place.
        mask_grid: Precomputed XOR values for one mask pattern.
        size: Width/height of the QR code.
    """
    for y in range(size):
        row_int = int.from_bytes(modules[y], "big")
        mask_int = int.from_bytes(mask_grid[y], "big")
        result_bytes = (row_int ^ mask_int).to_bytes(size, "big")
        modules[y] = bytearray(result_bytes)


# ---- Penalty scoring helpers (module-level for performance) ----


def _penalty_line_score(
    line: bytearray, size: int, penalty_n1: int, penalty_n3: int
) -> int:
    """Compute run-length and finder-pattern penalty for a single line.

    Evaluates adjacent same-color runs (rule 1) and finder-like 1:1:3:1:1
    patterns for one row or column of the QR code. Push/check logic is
    inlined to avoid per-pixel function call overhead in the hot loop.

    Args:
        line: A bytearray of module values (0 or 1) for one line.
        size: Length of the line.
        penalty_n1: Penalty constant for run-length violations.
        penalty_n3: Penalty constant for finder-like patterns.

    Returns:
        The penalty score for this line.
    """
    result = 0
    runcolor = 0
    runlen = 0
    rh0 = rh1 = rh2 = rh3 = rh4 = rh5 = rh6 = 0
    for i in range(size):
        c = line[i]
        if c == runcolor:
            runlen += 1
            if runlen == 5:
                result += penalty_n1
            elif runlen > 5:
                result += 1
            continue
        # Color changed: push run into history
        rl = runlen + size if rh0 == 0 else runlen
        rh6, rh5, rh4, rh3, rh2, rh1, rh0 = rh5, rh4, rh3, rh2, rh1, rh0, rl
        # Check for finder pattern (only after light runs)
        if not runcolor:
            result += _rh_finder_penalty(rh0, rh1, rh2, rh3, rh4, rh5, rh6, penalty_n3)
        runcolor = c
        runlen = 1
    result += _terminate_line(
        runcolor, runlen, rh0, rh1, rh2, rh3, rh4, rh5, rh6, size, penalty_n3
    )
    return result


def _rh_finder_penalty(
    rh0: int,
    rh1: int,
    rh2: int,
    rh3: int,
    rh4: int,
    rh5: int,
    rh6: int,
    penalty_n3: int,
) -> int:
    """Check run history for finder-like patterns (1:1:3:1:1 ratio).

    Called after a light run is pushed into the history. Checks both
    orientations of the finder pattern (light border on left or right).

    Args:
        rh0-rh6: Run history values (newest to oldest).
        penalty_n3: Penalty constant for finder patterns.

    Returns:
        Penalty points (0, penalty_n3, or 2*penalty_n3).
    """
    n = rh1
    if n <= 0 or rh2 != n or rh4 != n or rh5 != n or rh3 != n * 3:
        return 0
    result = 0
    if rh0 >= n * 4 and rh6 >= n:
        result += penalty_n3
    if rh6 >= n * 4 and rh0 >= n:
        result += penalty_n3
    return result


def _terminate_line(
    runcolor: int,
    runlen: int,
    rh0: int,
    rh1: int,
    rh2: int,
    rh3: int,
    rh4: int,
    rh5: int,
    rh6: int,
    size: int,
    penalty_n3: int,
) -> int:
    """Terminate a line and check for final finder patterns.

    Called once at the end of each line to finalize the run history
    and perform the final finder pattern check.

    Args:
        runcolor: Color of the current (last) run.
        runlen: Length of the current (last) run.
        rh0-rh6: Run history values.
        size: QR code size (for border padding).
        penalty_n3: Penalty constant for finder patterns.

    Returns:
        Penalty points from the final finder pattern check.
    """
    if runcolor:
        rl = runlen + size if rh0 == 0 else runlen
        rh6, rh5, rh4, rh3, rh2, rh1, rh0 = rh5, rh4, rh3, rh2, rh1, rh0, rl
        runlen = 0
    rl = runlen + size
    if rh0 == 0:
        rl += size
    rh6, rh5, rh4, rh3, rh2, rh1, rh0 = rh5, rh4, rh3, rh2, rh1, rh0, rl
    return _rh_finder_penalty(rh0, rh1, rh2, rh3, rh4, rh5, rh6, penalty_n3)


def _compute_penalty_rows(
    modules: list[bytearray],
    size: int,
    penalty_n1: int,
    penalty_n2: int,
    penalty_n3: int,
) -> tuple[int, int]:
    """Compute row-direction penalties (rule 1 runs, finder, 2x2 blocks, dark count).

    Evaluates horizontal run-length penalties, finder-like patterns (rule 1),
    2x2 same-color block penalties (rule 3), and counts dark modules (rule 4)
    in a single pass over rows.

    Args:
        modules: The QR code module grid.
        size: The size (width/height) of the QR code.
        penalty_n1: Penalty constant for run-length violations.
        penalty_n2: Penalty constant for 2x2 block violations.
        penalty_n3: Penalty constant for finder-like patterns.

    Returns:
        A tuple of (penalty_score, dark_count).
    """
    result = 0
    dark = 0
    prev_row = None

    for y in range(size):
        row = modules[y]
        dark += sum(row)
        result += _penalty_line_score(row, size, penalty_n1, penalty_n3)

        # Rule 3: 2x2 blocks (compare with previous row)
        if prev_row is not None:
            for x in range(size - 1):
                c = row[x]
                if c == row[x + 1] == prev_row[x] == prev_row[x + 1]:
                    result += penalty_n2
        prev_row = row

    return result, dark


def _compute_penalty_lines(
    lines: list[bytearray],
    size: int,
    penalty_n1: int,
    penalty_n3: int,
) -> int:
    """Compute run-length and finder-pattern penalties for a set of lines.

    Used for both row and column penalties — for columns, the caller
    transposes the grid first so this function always iterates row-major.

    Args:
        lines: List of bytearrays representing lines to evaluate.
        size: Length of each line.
        penalty_n1: Penalty constant for run-length violations.
        penalty_n3: Penalty constant for finder-like patterns.

    Returns:
        The line penalty score.
    """
    result = 0
    for line in lines:
        result += _penalty_line_score(line, size, penalty_n1, penalty_n3)
    return result


def _compute_penalty(
    modules: list[bytearray],
    size: int,
    penalty_n1: int,
    penalty_n2: int,
    penalty_n3: int,
    penalty_n4: int,
) -> int:
    """Compute the total penalty score for a QR code module grid.

    Combines all four penalty rules:
    - Rule 1: Adjacent modules in rows/columns with same color (runs of 5+).
    - Rule 2: Finder-like patterns in rows and columns (1:1:3:1:1 ratio).
    - Rule 3: 2x2 blocks of modules having same color.
    - Rule 4: Imbalance of dark and light modules.

    Transposes the module grid for the column pass so that column iteration
    uses contiguous memory access patterns.

    Args:
        modules: The QR code module grid.
        size: The size (width/height) of the QR code.
        penalty_n1: Penalty constant for run-length violations.
        penalty_n2: Penalty constant for 2x2 block violations.
        penalty_n3: Penalty constant for finder-like patterns.
        penalty_n4: Penalty constant for dark/light imbalance.

    Returns:
        The total penalty score.
    """
    # Row pass: horizontal runs, finder patterns, 2x2 blocks, dark count
    result, dark = _compute_penalty_rows(
        modules, size, penalty_n1, penalty_n2, penalty_n3
    )
    # Transpose for column pass: reuse row logic on transposed grid.
    columns = [bytearray(size) for _ in range(size)]
    for y in range(size):
        row = modules[y]
        for x in range(size):
            columns[x][y] = row[x]
    result += _compute_penalty_lines(columns, size, penalty_n1, penalty_n3)
    # Rule 4: dark/light imbalance
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    result += k * penalty_n4
    return result


# ---- QR Code symbol class ----


class QrCode:
    """A QR Code symbol, which is a type of two-dimension barcode.
    Invented by Denso Wave and described in the ISO/IEC 18004 standard.
    Instances of this class represent an immutable square grid of dark and light cells.
    The class provides static factory functions to create a QR Code from text or binary data.
    The class covers the QR Code Model 2 specification, supporting all versions (sizes)
    from 1 to 40, all 4 error correction levels, and 4 character encoding modes.

    Ways to create a QR Code object:
    - High level: Take the payload data and call QrCode.encode_text() or QrCode.encode_binary().
    - Mid level: Custom-make the list of segments and call QrCode.encode_segments().
    - Low level: Custom-make the array of data codeword bytes (including
      segment headers and final padding, excluding error correction codewords),
      supply the appropriate version number, and call the QrCode() constructor.
    (Note that all ways require supplying the desired error correction level.)"""

    # ---- Static factory functions (high level) ----

    @staticmethod
    def encode_text(text: str, ecl: QrCode.Ecc) -> QrCode:
        """Returns a QR Code representing the given Unicode text string at the given error correction level.
        As a conservative upper bound, this function is guaranteed to succeed for strings that have 738 or fewer
        Unicode code points (not UTF-16 code units) if the low error correction level is used. The smallest possible
        QR Code version is automatically chosen for the output. The ECC level of the result may be higher than the
        ecl argument if it can be done without increasing the version."""
        segs: list[QrSegment] = QrSegment.make_segments(text)
        return QrCode.encode_segments(segs, ecl)

    @staticmethod
    def encode_binary(data: Union[bytes, Sequence[int]], ecl: QrCode.Ecc) -> QrCode:
        """Returns a QR Code representing the given binary data at the given error correction level.
        This function always encodes using the binary segment mode, not any text mode. The maximum number of
        bytes allowed is 2953. The smallest possible QR Code version is automatically chosen for the output.
        The ECC level of the result may be higher than the ecl argument if it can be done without increasing the version."""
        return QrCode.encode_segments([QrSegment.make_bytes(data)], ecl)

    # ---- Static factory functions (mid level) ----

    @staticmethod
    def encode_segments(
        segs: Sequence[QrSegment],
        ecl: QrCode.Ecc,
        minversion: int = 1,
        maxversion: int = 40,
        mask: int = -1,
        boostecl: bool = True,
    ) -> QrCode:
        """Returns a QR Code representing the given segments with the given encoding parameters.
        The smallest possible QR Code version within the given range is automatically
        chosen for the output. Iff boostecl is true, then the ECC level of the result
        may be higher than the ecl argument if it can be done without increasing the
        version. The mask number is either between 0 to 7 (inclusive) to force that
        mask, or -1 to automatically choose an appropriate mask (which may be slow).
        This function allows the user to create a custom sequence of segments that switches
        between modes (such as alphanumeric and byte) to encode text in less space.
        This is a mid-level API; the high-level API is encode_text() and encode_binary()."""

        if not (
            QrCode.MIN_VERSION <= minversion <= maxversion <= QrCode.MAX_VERSION
        ) or not (-1 <= mask <= 7):
            raise ValueError("Invalid value")

        # Find the minimal version number to use
        for version in range(minversion, maxversion + 1):
            datacapacitybits: int = (
                QrCode._get_num_data_codewords(version, ecl) * 8
            )  # Number of data bits available
            datausedbits: int | None = QrSegment.get_total_bits(segs, version)
            if (datausedbits is not None) and (datausedbits <= datacapacitybits):
                break  # This version number is found to be suitable
            if (
                version >= maxversion
            ):  # All versions in the range could not fit the given data
                msg: str = "Segment too long"
                if datausedbits is not None:
                    msg = f"Data length = {datausedbits} bits, Max capacity = {datacapacitybits} bits"
                raise DataTooLongError(msg)
        assert datausedbits is not None

        # Increase the error correction level while the data still fits in the current version number
        for newecl in (
            QrCode.Ecc.MEDIUM,
            QrCode.Ecc.QUARTILE,
            QrCode.Ecc.HIGH,
        ):  # From low to high
            if boostecl and (
                datausedbits <= QrCode._get_num_data_codewords(version, newecl) * 8
            ):
                ecl = newecl

        # Concatenate all segments to create the data bit string
        bb = _BitBuffer()
        for seg in segs:
            bb.append_bits(seg.get_mode().get_mode_bits(), 4)
            bb.append_bits(
                seg.get_num_chars(), seg.get_mode().num_char_count_bits(version)
            )
            bb.extend(seg._bitdata)
        assert len(bb) == datausedbits

        # Add terminator and pad up to a byte if applicable
        datacapacitybits = QrCode._get_num_data_codewords(version, ecl) * 8
        assert len(bb) <= datacapacitybits
        bb.append_bits(0, min(4, datacapacitybits - len(bb)))
        bb.append_bits(
            0, -len(bb) % 8
        )  # Note: Python's modulo on negative numbers behaves better than C family languages
        assert len(bb) % 8 == 0

        # Pad with alternating bytes until data capacity is reached
        for padbyte in itertools.cycle((0xEC, 0x11)):
            if len(bb) >= datacapacitybits:
                break
            bb.append_bits(padbyte, 8)

        # Pack bits into bytes in big endian
        datacodewords = bb.pack_to_bytes()

        # Create the QR Code object
        return QrCode(version, ecl, datacodewords, mask)

    # ---- Private fields ----

    # The version number of this QR Code, which is between 1 and 40 (inclusive).
    # This determines the size of this barcode.
    _version: int

    # The width and height of this QR Code, measured in modules, between
    # 21 and 177 (inclusive). This is equal to version * 4 + 17.
    _size: int

    # The error correction level used in this QR Code.
    _errcorlvl: QrCode.Ecc

    # The index of the mask pattern used in this QR Code, which is between 0 and 7 (inclusive).
    # Even if a QR Code is created with automatic masking requested (mask = -1),
    # the resulting object still has a mask value between 0 and 7.
    _mask: int

    # The modules of this QR Code (0 = light, 1 = dark).
    # Stored as list of bytearrays for compact memory and fast iteration.
    # Immutable after constructor finishes. Accessed through get_module().
    _modules: list[bytearray]

    # Indicates function modules that are not subjected to masking.
    # Stored as list of bytearrays. Discarded when constructor finishes.
    _isfunction: list[bytearray]

    # ---- Constructor (low level) ----

    def __init__(
        self,
        version: int,
        errcorlvl: QrCode.Ecc,
        datacodewords: Union[bytes, Sequence[int]],
        msk: int,
    ) -> None:
        """Creates a new QR Code with the given version number,
        error correction level, data codeword bytes, and mask number.
        This is a low-level API that most users should not use directly.
        A mid-level API is the encode_segments() function."""

        # Check scalar arguments and set fields
        if not (QrCode.MIN_VERSION <= version <= QrCode.MAX_VERSION):
            raise ValueError("Version value out of range")
        if not (-1 <= msk <= 7):
            raise ValueError("Mask value out of range")

        self._version = version
        self._size = version * 4 + 17
        self._errcorlvl = errcorlvl

        # Initialize both grids to be size*size arrays of 0 (light)
        self._modules = [
            bytearray(self._size) for _ in range(self._size)
        ]  # Initially all light
        self._isfunction = [bytearray(self._size) for _ in range(self._size)]

        # Compute ECC, draw modules
        self._draw_function_patterns()
        allcodewords: bytes = self._add_ecc_and_interleave(bytearray(datacodewords))
        self._draw_codewords(allcodewords)

        # Do masking
        if msk == -1:  # Automatically choose best mask
            # Precompute mask grids to avoid per-pixel arithmetic and
            # isfunction checks during the 8-mask evaluation loop
            mask_grids = _build_mask_grids(self._isfunction, self._size)
            minpenalty: int = 1 << 32
            for i in range(8):
                _apply_precomputed_mask(self._modules, mask_grids[i], self._size)
                self._draw_format_bits(i)
                penalty = self._get_penalty_score()
                if penalty < minpenalty:
                    msk = i
                    minpenalty = penalty
                _apply_precomputed_mask(
                    self._modules, mask_grids[i], self._size
                )  # Undoes the mask due to XOR
            assert 0 <= msk <= 7
            self._mask = msk
            _apply_precomputed_mask(self._modules, mask_grids[msk], self._size)
        else:
            self._mask = msk
            self._apply_mask(msk)  # Apply the specified mask
        self._draw_format_bits(msk)  # Overwrite old format bits

        del self._isfunction

    # ---- Accessor methods ----

    def get_version(self) -> int:
        """Returns this QR Code's version number, in the range [1, 40]."""
        return self._version

    def get_size(self) -> int:
        """Returns this QR Code's size, in the range [21, 177]."""
        return self._size

    def get_error_correction_level(self) -> QrCode.Ecc:
        """Returns this QR Code's error correction level."""
        return self._errcorlvl

    def get_mask(self) -> int:
        """Returns this QR Code's mask, in the range [0, 7]."""
        return self._mask

    def get_module(self, x: int, y: int) -> bool:
        """Returns the color of the module (pixel) at the given coordinates, which is False
        for light or True for dark. The top left corner has the coordinates (x=0, y=0).
        If the given coordinates are out of bounds, then False (light) is returned."""
        return (
            (0 <= x < self._size) and (0 <= y < self._size) and self._modules[y][x] != 0
        )

    # ---- Private helper methods for constructor: Drawing function modules ----

    def _draw_function_patterns(self) -> None:
        """Reads this object's version field, and draws and marks all function modules."""
        # Draw horizontal and vertical timing patterns
        for i in range(self._size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        # Draw 3 finder patterns (all corners except bottom right; overwrites some timing modules)
        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(self._size - 4, 3)
        self._draw_finder_pattern(3, self._size - 4)

        # Draw numerous alignment patterns
        alignpatpos: list[int] = self._get_alignment_pattern_positions()
        numalign: int = len(alignpatpos)
        skips: Sequence[tuple[int, int]] = (
            (0, 0),
            (0, numalign - 1),
            (numalign - 1, 0),
        )
        for i in range(numalign):
            for j in range(numalign):
                if (i, j) not in skips:  # Don't draw on the three finder corners
                    self._draw_alignment_pattern(alignpatpos[i], alignpatpos[j])

        # Draw configuration data
        self._draw_format_bits(
            0
        )  # Dummy mask value; overwritten later in the constructor
        self._draw_version()

    def _draw_format_bits(self, mask: int) -> None:
        """Draws two copies of the format bits (with its own error correction code)
        based on the given mask and this object's error correction level field."""
        # Calculate error correction code and pack bits
        data: int = (
            self._errcorlvl.formatbits << 3 | mask
        )  # errCorrLvl is uint2, mask is uint3
        rem: int = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits: int = (data << 10 | rem) ^ 0x5412  # uint15
        assert bits >> 15 == 0

        # Inline module writes to avoid _set_function_module call overhead.
        # These cells are all function modules, so isfunction is already set.
        modules = self._modules
        size = self._size

        # Draw first copy
        for i in range(0, 6):
            modules[i][8] = (bits >> i) & 1
        modules[7][8] = (bits >> 6) & 1
        modules[8][8] = (bits >> 7) & 1
        modules[8][7] = (bits >> 8) & 1
        for i in range(9, 15):
            modules[8][14 - i] = (bits >> i) & 1

        # Draw second copy
        for i in range(0, 8):
            modules[8][size - 1 - i] = (bits >> i) & 1
        for i in range(8, 15):
            modules[size - 15 + i][8] = (bits >> i) & 1
        modules[size - 8][8] = 1  # Always dark

    def _draw_version(self) -> None:
        """Draws two copies of the version bits (with its own error correction code),
        based on this object's version field, iff 7 <= version <= 40."""
        if self._version < 7:
            return

        # Calculate error correction code and pack bits
        rem: int = self._version  # version is uint6, in the range [7, 40]
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits: int = self._version << 12 | rem  # uint18
        assert bits >> 18 == 0

        # Draw two copies
        for i in range(18):
            bit: int = _get_bit(bits, i)
            a: int = self._size - 11 + i % 3
            b: int = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        """Draws a 9*9 finder pattern including the border separator,
        with the center module at (x, y). Modules can be out of bounds."""
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                xx, yy = x + dx, y + dy
                if (0 <= xx < self._size) and (0 <= yy < self._size):
                    # Chebyshev/infinity norm
                    self._set_function_module(
                        xx, yy, max(abs(dx), abs(dy)) not in (2, 4)
                    )

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        """Draws a 5*5 alignment pattern, with the center module
        at (x, y). All modules must be in bounds."""
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set_function_module(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

    def _set_function_module(self, x: int, y: int, isdark: int | bool) -> None:
        """Sets the color of a module and marks it as a function module.
        Only used by the constructor. Coordinates must be in bounds."""
        self._modules[y][x] = 1 if isdark else 0
        self._isfunction[y][x] = 1

    # ---- Private helper methods for constructor: Codewords and masking ----

    def _add_ecc_and_interleave(self, data: bytearray) -> bytes:
        """Returns a new byte string representing the given data with the appropriate error correction
        codewords appended to it, based on this object's version and error correction level."""
        version: int = self._version
        assert len(data) == QrCode._get_num_data_codewords(version, self._errcorlvl)

        # Calculate parameter numbers
        numblocks: int = QrCode._NUM_ERROR_CORRECTION_BLOCKS[self._errcorlvl.ordinal][
            version
        ]
        blockecclen: int = QrCode._ECC_CODEWORDS_PER_BLOCK[self._errcorlvl.ordinal][
            version
        ]
        rawcodewords: int = QrCode._get_num_raw_data_modules(version) // 8
        numshortblocks: int = numblocks - rawcodewords % numblocks
        shortblocklen: int = rawcodewords // numblocks

        # Split data into blocks and append ECC to each block
        blocks: list[bytes] = []
        rsdiv: bytes = QrCode._reed_solomon_compute_divisor(blockecclen)
        k: int = 0
        for i in range(numblocks):
            dat: bytearray = data[
                k : k + shortblocklen - blockecclen + (0 if i < numshortblocks else 1)
            ]
            k += len(dat)
            ecc: bytes = QrCode._reed_solomon_compute_remainder(bytes(dat), rsdiv)
            if i < numshortblocks:
                dat.append(0)
            blocks.append(bytes(dat) + ecc)
        assert k == len(data)

        # Interleave (not concatenate) the bytes from every block into a single sequence
        result = bytearray()
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                # Skip the padding byte in short blocks
                if (i != shortblocklen - blockecclen) or (j >= numshortblocks):
                    result.append(blk[i])
        assert len(result) == rawcodewords
        return bytes(result)

    def _draw_codewords(self, data: bytes) -> None:
        """Draws the given sequence of 8-bit codewords (data and error correction) onto the entire
        data area of this QR Code. Function modules need to be marked off before this is called."""
        assert len(data) == QrCode._get_num_raw_data_modules(self._version) // 8

        i: int = 0  # Bit index into the data
        datalen8 = len(data) * 8
        modules = self._modules
        isfunction = self._isfunction
        size = self._size
        # Do the funny zigzag scan
        for right in range(
            size - 1, 0, -2
        ):  # Index of right column in each column pair
            if right <= 6:
                right -= 1
            for vert in range(size):  # Vertical counter
                for j in range(2):
                    x: int = right - j  # Actual x coordinate
                    upward: bool = (right + 1) & 2 == 0
                    y: int = (
                        (size - 1 - vert) if upward else vert
                    )  # Actual y coordinate
                    if (not isfunction[y][x]) and (i < datalen8):
                        modules[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1
                        i += 1
                    # If this QR Code has any remainder bits (0 to 7), they were assigned as
                    # 0/false/light by the constructor and are left unchanged by this method
        assert i == datalen8

    def _apply_mask(self, mask: int) -> None:
        """XORs the codeword modules in this QR Code with the given mask pattern.

        Used when a specific mask is requested (not auto-select). For auto-select,
        precomputed mask grids are used instead for better performance.

        The function modules must be marked and the codeword bits must be drawn
        before masking. Due to the arithmetic of XOR, calling _apply_mask() with
        the same mask value a second time will undo the mask. A final well-formed
        QR Code needs exactly one (not zero, two, etc.) mask applied.
        """
        if not (0 <= mask <= 7):
            raise ValueError("Mask value out of range")
        grids = _build_mask_grids(self._isfunction, self._size)
        _apply_precomputed_mask(self._modules, grids[mask], self._size)

    def _get_penalty_score(self) -> int:
        """Calculates and returns the penalty score based on state of this QR Code's current modules.

        Merges all four penalty rules into a single grid traversal to minimize
        iteration overhead. Maintains per-column state to compute vertical
        penalties during the row-major pass.

        This is used by the automatic mask choice algorithm to find the mask
        pattern that yields the lowest score.
        """
        result: int = _compute_penalty(
            self._modules,
            self._size,
            QrCode._PENALTY_N1,
            QrCode._PENALTY_N2,
            QrCode._PENALTY_N3,
            QrCode._PENALTY_N4,
        )
        assert (
            0 <= result <= 2568888
        )  # Non-tight upper bound based on default values of PENALTY_N1, ..., N4
        return result

    # ---- Private helper functions ----

    def _get_alignment_pattern_positions(self) -> list[int]:
        """Returns an ascending list of positions of alignment patterns for this version number.
        Each position is in the range [0,177), and are used on both the x and y axes.
        This could be implemented as lookup table of 40 variable-length lists of integers."""
        if self._version == 1:
            return []
        else:
            numalign: int = self._version // 7 + 2
            step: int = (self._version * 8 + numalign * 3 + 5) // (numalign * 4 - 4) * 2
            result: list[int] = [
                (self._size - 7 - i * step) for i in range(numalign - 1)
            ] + [6]
            return list(reversed(result))

    @staticmethod
    def _get_num_raw_data_modules(ver: int) -> int:
        """Returns the number of data bits that can be stored in a QR Code of the given version number, after
        all function modules are excluded. This includes remainder bits, so it might not be a multiple of 8.
        The result is in the range [208, 29648]. This could be implemented as a 40-entry lookup table."""
        if not (QrCode.MIN_VERSION <= ver <= QrCode.MAX_VERSION):
            raise ValueError("Version number out of range")
        result: int = (16 * ver + 128) * ver + 64
        if ver >= 2:
            numalign: int = ver // 7 + 2
            result -= (25 * numalign - 10) * numalign - 55
            if ver >= 7:
                result -= 36
        assert 208 <= result <= 29648
        return result

    @staticmethod
    def _get_num_data_codewords(ver: int, ecl: QrCode.Ecc) -> int:
        """Returns the number of 8-bit data (i.e. not error correction) codewords contained in any
        QR Code of the given version number and error correction level, with remainder bits discarded.
        This stateless pure function could be implemented as a (40*4)-cell lookup table."""
        return (
            QrCode._get_num_raw_data_modules(ver) // 8
            - QrCode._ECC_CODEWORDS_PER_BLOCK[ecl.ordinal][ver]
            * QrCode._NUM_ERROR_CORRECTION_BLOCKS[ecl.ordinal][ver]
        )

    @staticmethod
    def _reed_solomon_compute_divisor(degree: int) -> bytes:
        """Returns a Reed-Solomon ECC generator polynomial for the given degree. This could be
        implemented as a lookup table over all possible parameter values, instead of as an algorithm."""
        if not (1 <= degree <= 255):
            raise ValueError("Degree out of range")
        # Polynomial coefficients are stored from highest to lowest power, excluding the leading term which is always 1.
        # For example the polynomial x^3 + 255x^2 + 8x + 93 is stored as the uint8 array [255, 8, 93].
        result = bytearray([0] * (degree - 1) + [1])  # Start off with the monomial x^0

        # Compute the product polynomial (x - r^0) * (x - r^1) * (x - r^2) * ... * (x - r^{degree-1}),
        # and drop the highest monomial term which is always 1x^degree.
        # Note that r = 0x02, which is a generator element of this field GF(2^8/0x11D).
        root: int = 1
        gf_mul = _GF_MUL
        for _ in range(degree):  # Unused variable i
            # Multiply the current product by (x - r^i)
            root_row = gf_mul[root]
            for j in range(degree):
                result[j] = root_row[result[j]]
                if j + 1 < degree:
                    result[j] ^= result[j + 1]
            root = gf_mul[root][0x02]
        return bytes(result)

    @staticmethod
    def _reed_solomon_compute_remainder(data: bytes, divisor: bytes) -> bytes:
        """Returns the Reed-Solomon error correction codeword for the given data and divisor polynomials."""
        result = bytearray([0] * len(divisor))
        gf_mul = _GF_MUL
        for b in data:  # Polynomial division
            factor: int = b ^ result[0]
            del result[0]
            result.append(0)
            if factor != 0:
                factor_row = gf_mul[factor]
                for i, coef in enumerate(divisor):
                    result[i] ^= factor_row[coef]
        return bytes(result)

    @staticmethod
    def _reed_solomon_multiply(x: int, y: int) -> int:
        """Returns the product of the two given field elements modulo GF(2^8/0x11D). The arguments and result
        are unsigned 8-bit integers. Uses precomputed lookup table for O(1) performance."""
        return _GF_MUL[x][y]

    # ---- Constants and tables ----

    MIN_VERSION: int = (
        1  # The minimum version number supported in the QR Code Model 2 standard
    )
    MAX_VERSION: int = (
        40  # The maximum version number supported in the QR Code Model 2 standard
    )

    # For use in _get_penalty_score(), when evaluating which mask is best.
    _PENALTY_N1: int = 3
    _PENALTY_N2: int = 3
    _PENALTY_N3: int = 40
    _PENALTY_N4: int = 10

    _ECC_CODEWORDS_PER_BLOCK: Sequence[Sequence[int]] = (
        # Version: (note that index 0 is for padding, and is set to an illegal value)
        # 0,  1,  2,  3,  4,  5,  6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40    Error correction level
        (
            -1,
            7,
            10,
            15,
            20,
            26,
            18,
            20,
            24,
            30,
            18,
            20,
            24,
            26,
            30,
            22,
            24,
            28,
            30,
            28,
            28,
            28,
            28,
            30,
            30,
            26,
            28,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
        ),  # Low
        (
            -1,
            10,
            16,
            26,
            18,
            24,
            16,
            18,
            22,
            22,
            26,
            30,
            22,
            22,
            24,
            24,
            28,
            28,
            26,
            26,
            26,
            26,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
            28,
        ),  # Medium
        (
            -1,
            13,
            22,
            18,
            26,
            18,
            24,
            18,
            22,
            20,
            24,
            28,
            26,
            24,
            20,
            30,
            24,
            28,
            28,
            26,
            30,
            28,
            30,
            30,
            30,
            30,
            28,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
        ),  # Quartile
        (
            -1,
            17,
            28,
            22,
            16,
            22,
            28,
            26,
            26,
            24,
            28,
            24,
            28,
            22,
            24,
            24,
            30,
            28,
            28,
            26,
            28,
            30,
            24,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
            30,
        ),
    )  # High

    _NUM_ERROR_CORRECTION_BLOCKS: Sequence[Sequence[int]] = (
        # Version: (note that index 0 is for padding, and is set to an illegal value)
        # 0, 1, 2, 3, 4, 5, 6, 7, 8, 9,10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40    Error correction level
        (
            -1,
            1,
            1,
            1,
            1,
            1,
            2,
            2,
            2,
            2,
            4,
            4,
            4,
            4,
            4,
            6,
            6,
            6,
            6,
            7,
            8,
            8,
            9,
            9,
            10,
            12,
            12,
            12,
            13,
            14,
            15,
            16,
            17,
            18,
            19,
            19,
            20,
            21,
            22,
            24,
            25,
        ),  # Low
        (
            -1,
            1,
            1,
            1,
            2,
            2,
            4,
            4,
            4,
            5,
            5,
            5,
            8,
            9,
            9,
            10,
            10,
            11,
            13,
            14,
            16,
            17,
            17,
            18,
            20,
            21,
            23,
            25,
            26,
            28,
            29,
            31,
            33,
            35,
            37,
            38,
            40,
            43,
            45,
            47,
            49,
        ),  # Medium
        (
            -1,
            1,
            1,
            2,
            2,
            4,
            4,
            6,
            6,
            8,
            8,
            8,
            10,
            12,
            16,
            12,
            17,
            16,
            18,
            21,
            20,
            23,
            23,
            25,
            27,
            29,
            34,
            34,
            35,
            38,
            40,
            43,
            45,
            48,
            51,
            53,
            56,
            59,
            62,
            65,
            68,
        ),  # Quartile
        (
            -1,
            1,
            1,
            2,
            4,
            4,
            4,
            5,
            6,
            8,
            8,
            11,
            11,
            16,
            16,
            18,
            16,
            19,
            21,
            25,
            25,
            25,
            34,
            30,
            32,
            35,
            37,
            40,
            42,
            45,
            48,
            51,
            54,
            57,
            60,
            63,
            66,
            70,
            74,
            77,
            81,
        ),
    )  # High

    _MASK_PATTERNS: Sequence[Callable[[int, int], int]] = (
        (lambda x, y: (x + y) % 2),
        (lambda x, y: y % 2),
        (lambda x, y: x % 3),
        (lambda x, y: (x + y) % 3),
        (lambda x, y: (x // 3 + y // 2) % 2),
        (lambda x, y: x * y % 2 + x * y % 3),
        (lambda x, y: (x * y % 2 + x * y % 3) % 2),
        (lambda x, y: ((x + y) % 2 + x * y % 3) % 2),
    )

    # ---- Public helper enumeration ----

    class Ecc:
        ordinal: int  # (Public) In the range 0 to 3 (unsigned 2-bit integer)
        formatbits: (
            int  # (Package-private) In the range 0 to 3 (unsigned 2-bit integer)
        )

        """The error correction level in a QR Code symbol. Immutable."""

        # Private constructor
        def __init__(self, i: int, fb: int) -> None:
            self.ordinal = i
            self.formatbits = fb

        # Placeholders
        LOW: QrCode.Ecc
        MEDIUM: QrCode.Ecc
        QUARTILE: QrCode.Ecc
        HIGH: QrCode.Ecc

    # Public constants. Create them outside the class.
    Ecc.LOW = Ecc(0, 1)  # The QR Code can tolerate about  7% erroneous codewords
    Ecc.MEDIUM = Ecc(1, 0)  # The QR Code can tolerate about 15% erroneous codewords
    Ecc.QUARTILE = Ecc(2, 3)  # The QR Code can tolerate about 25% erroneous codewords
    Ecc.HIGH = Ecc(3, 2)  # The QR Code can tolerate about 30% erroneous codewords


# ---- Data segment class ----


class QrSegment:
    """A segment of character/binary/control data in a QR Code symbol.
    Instances of this class are immutable.
    The mid-level way to create a segment is to take the payload data
    and call a static factory function such as QrSegment.make_numeric().
    The low-level way to create a segment is to custom-make the bit buffer
    and call the QrSegment() constructor with appropriate values.
    This segment class imposes no length restrictions, but QR Codes have restrictions.
    Even in the most favorable conditions, a QR Code can only hold 7089 characters of data.
    Any segment longer than this is meaningless for the purpose of generating QR Codes."""

    # ---- Static factory functions (mid level) ----

    @staticmethod
    def make_bytes(data: Union[bytes, Sequence[int]]) -> QrSegment:
        """Returns a segment representing the given binary data encoded in byte mode.
        All input byte lists are acceptable. Any text string can be converted to
        UTF-8 bytes (s.encode("UTF-8")) and encoded as a byte mode segment."""
        bb = _BitBuffer()
        for b in data:
            bb.append_bits(b, 8)
        return QrSegment(QrSegment.Mode.BYTE, len(data), bb)

    @staticmethod
    def make_numeric(digits: str) -> QrSegment:
        """Returns a segment representing the given string of decimal digits encoded in numeric mode."""
        if not QrSegment.is_numeric(digits):
            raise ValueError("String contains non-numeric characters")
        bb = _BitBuffer()
        i: int = 0
        while i < len(digits):  # Consume up to 3 digits per iteration
            n: int = min(len(digits) - i, 3)
            bb.append_bits(int(digits[i : i + n]), n * 3 + 1)
            i += n
        return QrSegment(QrSegment.Mode.NUMERIC, len(digits), bb)

    @staticmethod
    def make_alphanumeric(text: str) -> QrSegment:
        """Returns a segment representing the given text string encoded in alphanumeric mode.
        The characters allowed are: 0 to 9, A to Z (uppercase only), space,
        dollar, percent, asterisk, plus, hyphen, period, slash, colon."""
        if not QrSegment.is_alphanumeric(text):
            raise ValueError(
                "String contains unencodable characters in alphanumeric mode"
            )
        bb = _BitBuffer()
        for i in range(0, len(text) - 1, 2):  # Process groups of 2
            temp: int = QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[i]] * 45
            temp += QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[i + 1]]
            bb.append_bits(temp, 11)
        if len(text) % 2 > 0:  # 1 character remaining
            bb.append_bits(QrSegment._ALPHANUMERIC_ENCODING_TABLE[text[-1]], 6)
        return QrSegment(QrSegment.Mode.ALPHANUMERIC, len(text), bb)

    @staticmethod
    def make_segments(text: str) -> list[QrSegment]:
        """Returns a new mutable list of zero or more segments to represent the given Unicode text string.
        The result may use various segment modes and switch modes to optimize the length of the bit stream."""

        # Select the most efficient segment encoding automatically
        if text == "":
            return []
        elif QrSegment.is_numeric(text):
            return [QrSegment.make_numeric(text)]
        elif QrSegment.is_alphanumeric(text):
            return [QrSegment.make_alphanumeric(text)]
        else:
            return [QrSegment.make_bytes(text.encode("UTF-8"))]

    @staticmethod
    def make_eci(assignval: int) -> QrSegment:
        """Returns a segment representing an Extended Channel Interpretation
        (ECI) designator with the given assignment value."""
        bb = _BitBuffer()
        if assignval < 0:
            raise ValueError("ECI assignment value out of range")
        elif assignval < (1 << 7):
            bb.append_bits(assignval, 8)
        elif assignval < (1 << 14):
            bb.append_bits(0b10, 2)
            bb.append_bits(assignval, 14)
        elif assignval < 1000000:
            bb.append_bits(0b110, 3)
            bb.append_bits(assignval, 21)
        else:
            raise ValueError("ECI assignment value out of range")
        return QrSegment(QrSegment.Mode.ECI, 0, bb)

    # Tests whether the given string can be encoded as a segment in numeric mode.
    # A string is encodable iff each character is in the range 0 to 9.
    @staticmethod
    def is_numeric(text: str) -> bool:
        return QrSegment._NUMERIC_REGEX.fullmatch(text) is not None

    # Tests whether the given string can be encoded as a segment in alphanumeric mode.
    # A string is encodable iff each character is in the following set: 0 to 9, A to Z
    # (uppercase only), space, dollar, percent, asterisk, plus, hyphen, period, slash, colon.
    @staticmethod
    def is_alphanumeric(text: str) -> bool:
        return QrSegment._ALPHANUMERIC_REGEX.fullmatch(text) is not None

    # ---- Private fields ----

    # The mode indicator of this segment. Accessed through get_mode().
    _mode: QrSegment.Mode

    # The length of this segment's unencoded data. Measured in characters for
    # numeric/alphanumeric/kanji mode, bytes for byte mode, and 0 for ECI mode.
    # Always zero or positive. Not the same as the data's bit length.
    # Accessed through get_num_chars().
    _numchars: int

    # The data bits of this segment. Accessed through get_data().
    _bitdata: _BitBuffer

    # ---- Constructor (low level) ----

    def __init__(
        self,
        mode: QrSegment.Mode,
        numch: int,
        bitdata: Union[_BitBuffer, Sequence[int]],
    ) -> None:
        """Creates a new QR Code segment with the given attributes and data.
        The character count (numch) must agree with the mode and the bit buffer length,
        but the constraint isn't checked. The given bit buffer is cloned and stored."""
        if numch < 0:
            raise ValueError()
        self._mode = mode
        self._numchars = numch
        if isinstance(bitdata, _BitBuffer):
            self._bitdata = _BitBuffer(bitdata._data, bitdata._length)
        else:
            bb = _BitBuffer()
            for bit in bitdata:
                bb._data = (bb._data << 1) | bit
                bb._length += 1
            self._bitdata = bb

    # ---- Accessor methods ----

    def get_mode(self) -> QrSegment.Mode:
        """Returns the mode field of this segment."""
        return self._mode

    def get_num_chars(self) -> int:
        """Returns the character count field of this segment."""
        return self._numchars

    def get_data(self) -> list[int]:
        """Returns a new copy of the data bits of this segment."""
        return list(self._bitdata)  # Make defensive copy

    # Package-private function
    @staticmethod
    def get_total_bits(segs: Sequence[QrSegment], version: int) -> int | None:
        """Calculates the number of bits needed to encode the given segments at
        the given version. Returns a non-negative number if successful. Otherwise
        returns None if a segment has too many characters to fit its length field."""
        result = 0
        for seg in segs:
            ccbits: int = seg.get_mode().num_char_count_bits(version)
            if seg.get_num_chars() >= (1 << ccbits):
                return None  # The segment's length doesn't fit the field's bit width
            result += 4 + ccbits + len(seg._bitdata)
        return result

    # ---- Constants ----

    # Describes precisely all strings that are encodable in numeric mode.
    _NUMERIC_REGEX: re.Pattern[str] = re.compile(r"[0-9]*")

    # Describes precisely all strings that are encodable in alphanumeric mode.
    _ALPHANUMERIC_REGEX: re.Pattern[str] = re.compile(r"[A-Z0-9 $%*+./:-]*")

    # Dictionary of "0"->0, "A"->10, "$"->37, etc.
    _ALPHANUMERIC_ENCODING_TABLE: dict[str, int] = {
        ch: i for (i, ch) in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:")
    }

    # ---- Public helper enumeration ----

    class Mode:
        """Describes how a segment's data bits are interpreted. Immutable."""

        _modebits: (
            int  # The mode indicator bits, which is a uint4 value (range 0 to 15)
        )
        _charcounts: tuple[
            int, int, int
        ]  # Number of character count bits for three different version ranges

        # Private constructor
        def __init__(self, modebits: int, charcounts: tuple[int, int, int]):
            self._modebits = modebits
            self._charcounts = charcounts

        # Package-private method
        def get_mode_bits(self) -> int:
            """Returns an unsigned 4-bit integer value (range 0 to 15) representing the mode indicator bits for this mode object."""
            return self._modebits

        # Package-private method
        def num_char_count_bits(self, ver: int) -> int:
            """Returns the bit width of the character count field for a segment in this mode
            in a QR Code at the given version number. The result is in the range [0, 16]."""
            return self._charcounts[(ver + 7) // 17]

        # Placeholders
        NUMERIC: QrSegment.Mode
        ALPHANUMERIC: QrSegment.Mode
        BYTE: QrSegment.Mode
        KANJI: QrSegment.Mode
        ECI: QrSegment.Mode

    # Public constants. Create them outside the class.
    Mode.NUMERIC = Mode(0x1, (10, 12, 14))
    Mode.ALPHANUMERIC = Mode(0x2, (9, 11, 13))
    Mode.BYTE = Mode(0x4, (8, 16, 16))
    Mode.KANJI = Mode(0x8, (8, 10, 12))
    Mode.ECI = Mode(0x7, (0, 0, 0))


# ---- Private helper class ----


class _BitBuffer:
    """An appendable sequence of bits (0s and 1s) stored as a single big integer.

    Uses integer bit-shift operations instead of per-bit list elements to
    minimize memory allocation and improve performance.
    """

    __slots__ = ("_data", "_length")

    def __init__(self, data: int = 0, length: int = 0) -> None:
        self._data: int = data
        self._length: int = length

    def append_bits(self, val: int, n: int) -> None:
        """Appends the given number of low-order bits of the given
        value to this buffer. Requires n >= 0 and 0 <= val < 2^n."""
        if (n < 0) or (val >> n != 0):
            raise ValueError("Value out of range")
        self._data = (self._data << n) | val
        self._length += n

    def extend(self, bits: Union[_BitBuffer, Sequence[int]]) -> None:
        """Appends each bit (0 or 1) from the iterable to this buffer."""
        if isinstance(bits, _BitBuffer):
            # Fast path: merge two _BitBuffers using bit operations
            self._data = (self._data << bits._length) | bits._data
            self._length += bits._length
        else:
            data = self._data
            length = self._length
            for b in bits:
                data = (data << 1) | b
                length += 1
            self._data = data
            self._length = length

    def __len__(self) -> int:
        return self._length

    def __iter__(self):  # type: ignore[override]
        """Iterates bits from MSB to LSB."""
        data = self._data
        for i in range(self._length - 1, -1, -1):
            yield (data >> i) & 1

    def pack_to_bytes(self) -> bytearray:
        """Packs bits into bytes in big-endian order (MSB first).

        Returns:
            A bytearray where each byte contains 8 consecutive bits.
            The buffer length must be a multiple of 8.
        """
        length = self._length
        data = self._data
        num_bytes = length >> 3
        result = bytearray(num_bytes)
        for i in range(num_bytes - 1, -1, -1):
            result[i] = data & 0xFF
            data >>= 8
        return result


def _get_bit(x: int, i: int) -> int:
    """Returns 1 if the i'th bit of x is set, 0 otherwise."""
    return (x >> i) & 1


class DataTooLongError(ValueError):
    """Raised when the supplied data does not fit any QR Code version. Ways to handle this exception include:
    - Decrease the error correction level if it was greater than Ecc.LOW.
    - If the encode_segments() function was called with a maxversion argument, then increase
      it if it was less than QrCode.MAX_VERSION. (This advice does not apply to the other
      factory functions because they search all versions up to QrCode.MAX_VERSION.)
    - Split the text data into better or optimal segments in order to reduce the number of bits required.
    - Change the text or binary data to be shorter.
    - Change the text to fit the character set of a particular segment mode (e.g. alphanumeric).
    - Propagate the error upward to the caller/user."""

    pass


# ---- Terminal rendering (added by WeiLink) ----


def print_qr_terminal(text: str) -> None:
    """Encode text as QR code and print to terminal using Unicode block characters.

    Uses half-block characters to render two rows per line for compact output.
    """
    qr = QrCode.encode_text(text, QrCode.Ecc.LOW)
    size = qr.get_size()
    border = 1

    # Use upper-half-block: "▀", lower-half-block: "▄", full block: "█", space: " "
    BOTH_DARK = "█"
    TOP_DARK = "▀"
    BOT_DARK = "▄"
    BOTH_LIGHT = " "

    lines: list[str] = []
    # Process two rows at a time
    for y in range(-border, size + border, 2):
        row_chars: list[str] = []
        for x in range(-border, size + border):
            top = qr.get_module(x, y)
            bot = qr.get_module(x, y + 1) if (y + 1) < (size + border) else False
            if top and bot:
                row_chars.append(BOTH_DARK)
            elif top:
                row_chars.append(TOP_DARK)
            elif bot:
                row_chars.append(BOT_DARK)
            else:
                row_chars.append(BOTH_LIGHT)
        lines.append("".join(row_chars))

    print("\n".join(lines))


# ---- Sibling import helpers ----


def _ensure_sibling_path(name: str) -> str:
    """Return the sibling module directory and prepend it to ``sys.path``."""
    sibling_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", name)
    if sibling_dir not in sys.path:
        sys.path.insert(0, sibling_dir)
    return sibling_dir


def _load_png_encoder():
    """Load sibling ``png`` module's ``Image`` and ``encode_png`` on demand."""
    _ensure_sibling_path("png")
    sys.modules.pop("png", None)
    try:
        from png import Image, encode_png
    except ImportError as exc:
        raise ImportError(
            "qr_to_png requires the sibling png module. "
            "Copy png/png.py into your project."
        ) from exc
    return Image, encode_png


# ---- Image output ----


def qr_to_svg(
    qr: QrCode,
    dest: str | os.PathLike[str] | None = None,
    *,
    scale: int = 10,
    border: int = 4,
    fg_color: str = "#000000",
    bg_color: str = "#ffffff",
) -> str | None:
    """Render a QR Code as an SVG image.

    Args:
        qr: QR Code to render.
        dest: File path to write SVG to, or ``None`` to return the SVG string.
        scale: Size of each QR module in SVG user units.
        border: Width of the quiet zone in QR modules.
        fg_color: CSS color for dark modules.
        bg_color: CSS color for light modules.

    Returns:
        SVG string when *dest* is ``None``, otherwise ``None``.
    """
    size = qr.get_size()
    total = (size + 2 * border) * scale

    # Build a single <path> collecting all dark modules.
    parts: list[str] = []
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                px = (x + border) * scale
                py = (y + border) * scale
                parts.append(f"M{px},{py}h{scale}v{scale}h-{scale}z")
    path_d = "".join(parts)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {total} {total}" '
        f'width="{total}" height="{total}">\n'
        f'<rect width="100%" height="100%" fill="{bg_color}"/>\n'
        f'<path d="{path_d}" fill="{fg_color}"/>\n'
        f"</svg>\n"
    )

    if dest is None:
        return svg
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(svg)
    return None


def qr_to_png(
    qr: QrCode,
    dest: str | os.PathLike[str] | None = None,
    *,
    scale: int = 10,
    border: int = 4,
    fg_color: int = 0,
    bg_color: int = 255,
) -> bytes | None:
    """Render a QR Code as a PNG image.

    Requires the sibling ``png`` module.

    Args:
        qr: QR Code to render.
        dest: File path to write PNG to, or ``None`` to return PNG bytes.
        scale: Pixels per QR module.
        border: Width of the quiet zone in QR modules.
        fg_color: Grayscale value (0--255) for dark modules.
        bg_color: Grayscale value (0--255) for light modules.

    Returns:
        PNG bytes when *dest* is ``None``, otherwise ``None``.

    Raises:
        ImportError: If the sibling ``png`` module is not available.
        ValueError: If *fg_color* or *bg_color* is outside 0--255.
    """
    if not (0 <= fg_color <= 255):
        raise ValueError(f"fg_color must be 0-255, got {fg_color}")
    if not (0 <= bg_color <= 255):
        raise ValueError(f"bg_color must be 0-255, got {bg_color}")

    Image, encode_png = _load_png_encoder()

    size = qr.get_size()
    total_px = (size + 2 * border) * scale

    # Build grayscale pixel buffer.
    fg_run = bytes([fg_color]) * scale
    pixels = bytearray([bg_color]) * (total_px * total_px)
    for y in range(size):
        for x in range(size):
            if qr.get_module(x, y):
                px = (x + border) * scale
                py = (y + border) * scale
                for row in range(py, py + scale):
                    offset = row * total_px + px
                    pixels[offset : offset + scale] = fg_run

    img = Image(width=total_px, height=total_px, data=bytes(pixels), mode="L")
    return encode_png(img, dest)
