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

import git

from progress.bar import Bar
from progress.spinner import Spinner


class CountingSpinner(Spinner):
    """
    Improved default Spinner with numerical progress
    """
    def __init__(self, message, **kwargs):
        """
        Extend object with `count` attribute

        :param message:
            Message printed before spinner.
        :param kwargs:
            Key arguments passed to Spinner base class.
        """
        super().__init__(message, **kwargs)
        self.count = 0

    def next(self, n=1):
        """
        Progress to next value

        :param n:
            Value is added to current `count`
        """
        self.count += n
        super().next()

    def write(self, s):
        """
        Override write method to add `count` value to the output

        :param s:
            Original spinner character.
        """
        super().write(" {} {}".format(s, self.count))


class RepoProgressPrinter(git.RemoteProgress):
    """
    Extended progress printer for `git` with progress bar and spinner
    """
    operation = {
        git.RemoteProgress.COUNTING: 'Counting objects',
        git.RemoteProgress.COMPRESSING: 'Compressing objects',
        git.RemoteProgress.WRITING: 'Writing',
        git.RemoteProgress.RECEIVING: 'Receiving objects',
        git.RemoteProgress.RESOLVING: 'Resolving deltas',
        git.RemoteProgress.FINDING_SOURCES: 'Finding sources',
        git.RemoteProgress.CHECKING_OUT: 'Checking out'
    }

    def __init__(self):
        """
        Initialize progress printer
        """
        super().__init__()
        self._progress = None
        self._last_count = 0

    def update(self, op_code, cur_count, max_count=None, message=''):
        """
        Callback method called when `git` returns some progress

        :param op_code:
            Opcode with operation code and stage (BEGIN, END).
        :param cur_count:
            Current value of progress.
        :param max_count:
            Maximal value of progress.
        :param message:
            Message returned for some operation codes.
        """
        cur_count = int(cur_count)
        max_count = max_count and int(max_count)
        op_id = op_code & self.OP_MASK
        stage_id = op_code & self.STAGE_MASK
        if stage_id & self.BEGIN:
            op_msg = self.operation[op_id]
            if max_count:
                self._progress = Bar(op_msg, max=max_count)
                self._last_count = 0
            else:
                self._progress = CountingSpinner(op_msg)
        self._progress.next(n=cur_count-self._last_count)
        self._last_count = cur_count
        if stage_id & self.END:
            self._progress.finish()
