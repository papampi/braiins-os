# Copyright (C) 2018  Braiins Systems s.r.o.
#
# This file is part of Braiins Build System (BB).
#
# BB is free software: you can redistribute it and/or modify
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from itertools import chain
from collections import OrderedDict


class Packages:
    """
    Class for parsing LEDE feeds index with packages
    """
    def __init__(self, path):
        """
        Initialize parser with path to feeds index file

        :param path:
            File path to feeds index file.
        """
        self._path = path
        self._input = None

    def __enter__(self):
        """
        Open feeds index file

        :return:
            Feeds index file parser.
        """
        self._input = open(self._path, 'r')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Close previously opend feeds index file
        """
        self._input.close()

    def _get_package_record(self, stream):
        """

        :param stream:
        :return:
        """
        package = OrderedDict()
        attribute = None
        value = None
        for line in stream:
            if not len(line) or line[0] == '\n':
                # end of record
                break
            if not line[0].isspace():
                # found new package attribute
                if attribute:
                    # store previous attribute
                    package[attribute] = value
                # attribute has format 'name: value\n'
                attribute, value = line.split(': ', 1)
                # remove newline
                value = value.rstrip()
            else:
                # when newline starts with space then previous attribute value continues
                value = '{}\n{}'.format(value, line.rstrip())
        if attribute:
            # store previous attribute
            package[attribute] = value
        return package

    def __iter__(self):
        """
        Iterate through all package records in feeds index file

        :return:
            Ordered dictionary with attribute records for one package.
        """
        while True:
            # find first attribute
            for line in self._input:
                if len(line) and not line[0].isspace():
                    break
            else:
                # no more data so break outer cycle
                break
            # read the whole record
            yield self._get_package_record(chain((line,), self._input))
