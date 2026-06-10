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
This module implements export of an (image, text) dataset for fine-tuning
the handwriting recognition (OCR) model.
"""

from sdaps import model
from sdaps import script

from sdaps.cmdline import export_subparser

from sdaps.utils.ugettext import ugettext, ungettext
_ = ugettext


export = export_subparser.add_parser('ocr-training',
    help=_("Export an (image, text) dataset for OCR model training."),
    description=_("""Export an (image, text) pair for every textbox where
    handwriting was detected during recognition. The image is the crop that
    was used as input to the OCR model, and the text is taken from
    data.text, i.e. the OCR result, possibly corrected by hand via "sdaps
    gui". Use a filter (e.g. "verified") to only export sheets that have
    been reviewed by a human. The resulting "manifest.csv" plus "images/"
    directory can be used to fine-tune the OCR model."""))
script.add_project_argument(export)

export.add_argument('-o', '--output',
    help=_("Directory to store the dataset in (default: <project>/ocr_training_export)"))
export.add_argument('-f', '--filter',
    help=_("Filter to only export a partial dataset, e.g. \"verified\" to only export reviewed sheets."))
export.set_defaults(direction='export')


@script.connect(export)
@script.logfile
def ocrtraining_export(cmdline):
    from sdaps import ocrtraining

    survey = model.survey.Survey.load(cmdline['project'])

    output_dir = cmdline['output'] or survey.path('ocr_training_export')

    count = ocrtraining.export(survey, output_dir, filter=cmdline['filter'])

    print(_("Exported %i (image, text) pairs to %s") % (count, output_dir))
