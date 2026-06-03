# -*- coding: utf-8 -*-
# SDAPS - Scripts for data acquisition with paper based surveys
# Copyright(C) 2008, Christoph Simon <post@christoph-simon.eu>
# Copyright(C) 2008, Benjamin Berg <benjamin@sipsolutions.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import cairo
import numpy as np

from sdaps import defs
from sdaps import log

_reader = None
_reader_languages = None
_ocr_available = None  # None=untried, True=ok, False=unavailable


def _get_reader():
    global _reader, _reader_languages, _ocr_available

    if _ocr_available is False:
        return None

    languages = list(defs.ocr_languages)

    if _reader is not None and _reader_languages == languages:
        return _reader

    try:
        import easyocr
        _reader = easyocr.Reader(languages)
        _reader_languages = languages
        _ocr_available = True
        return _reader
    except ImportError:
        if _ocr_available is None:
            log.warn("EasyOCR is not installed; text box content will not be recognized.")
        _ocr_available = False
        return None


def read_text_from_surface(surface, matrix, x, y, width, height):
    """Run EasyOCR on a rectangular region of a cairo A1 surface.

    Coordinates and dimensions are in mm; matrix maps mm to pixels.
    Returns the recognised text as a string, or None if OCR is unavailable
    or no text was found.
    """
    reader = _get_reader()
    if reader is None:
        return None

    img = _extract_region(surface, matrix, x, y, width, height)
    if img is None:
        return None

    results = reader.readtext(img, detail=0, paragraph=True)
    if results:
        return '\n'.join(results)
    return None


def _extract_region(surface, matrix, x, y, width, height):
    """Extract a region from a cairo A1 surface as a greyscale numpy array.

    The A1 surface is rendered onto an RGB24 canvas (black ink, white paper)
    and the region is returned as a (H, W) uint8 array suitable for EasyOCR.
    """
    # Transform mm bounding box to pixel coordinates
    px0, py0 = matrix.transform_point(x, y)
    px1, py1 = matrix.transform_point(x + width, y + height)

    left = int(max(0, min(px0, px1)))
    top = int(max(0, min(py0, py1)))
    right = int(min(surface.get_width(), max(px0, px1)))
    bottom = int(min(surface.get_height(), max(py0, py1)))

    crop_w = right - left
    crop_h = bottom - top

    if crop_w <= 0 or crop_h <= 0:
        return None

    # Render the A1 source into an RGB24 crop: white background, black ink.
    # cairo.mask_surface lets bits that are set (ink) paint through the black
    # source colour; unset bits (paper) stay white from the background paint.
    stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_RGB24, crop_w)
    buf = np.empty((crop_h, stride // 4), dtype=np.uint32)
    tmp = cairo.ImageSurface.create_for_data(buf.data, cairo.FORMAT_RGB24, crop_w, crop_h, stride)

    cr = cairo.Context(tmp)
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    cr.set_source_rgb(0, 0, 0)
    cr.mask_surface(surface, -left, -top)
    del cr
    tmp.flush()
    del tmp

    # Pull out the red channel as an 8-bit greyscale image
    grey = np.empty((crop_h, crop_w), dtype=np.uint8)
    grey[:, :] = (buf[:, :crop_w] >> 16) & 0xff
    return grey
