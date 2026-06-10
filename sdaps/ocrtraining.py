# -*- coding: utf-8 -*-
# SDAPS - Scripts for data acquisition with paper based surveys
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

"""
Export (image, text) pairs collected during handwriting recognition.

During `recognize`, every textbox that was detected as written-on has its
crop saved to disk (`data.ocr_image`), together with an initial guess at
`data.text` from the OCR model. A human reviewer can correct `data.text` via
`sdaps gui`. This module exports the resulting (image, text) pairs so they can
be used as a training/fine-tuning dataset for the OCR model.
"""

import csv
import os
import re
import shutil

from sdaps import clifilter
from sdaps import model


def _sanitize(name):
    return re.sub(r'[^A-Za-z0-9_.-]', '_', str(name))


def export(survey, output_dir, filter=None):
    filter = clifilter.clifilter(survey, filter)

    images_dir = os.path.join(output_dir, 'images')
    os.makedirs(images_dir, exist_ok=True)

    manifest = open(os.path.join(output_dir, 'manifest.csv'), 'w', encoding='utf-8', newline='')
    writer = csv.DictWriter(manifest, ['image', 'text', 'questionnaire_id', 'field'])
    writer.writeheader()

    count = [0]

    def export_sheet():
        sheet = survey.sheet
        for qobject in survey.questionnaire.qobjects:
            if not hasattr(qobject, 'boxes'):
                continue
            for box in qobject.boxes:
                if not isinstance(box, model.questionnaire.Textbox):
                    continue
                if not box.data.ocr_image or not box.data.text:
                    continue

                src = survey.path(box.data.ocr_image)
                if not os.path.exists(src):
                    continue

                dest_name = '%s_%s.png' % (_sanitize(sheet.questionnaire_id), box.id_csv())
                shutil.copy(src, os.path.join(images_dir, dest_name))

                writer.writerow({
                    'image': os.path.join('images', dest_name),
                    'text': box.data.text,
                    'questionnaire_id': sheet.questionnaire_id,
                    'field': box.id_csv(),
                })
                count[0] += 1

    survey.iterate(export_sheet, filter)

    manifest.close()

    return count[0]
