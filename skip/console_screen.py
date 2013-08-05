"""A simple console-based view for a Scratch interpreter."""

# Copyright (C) 2013 Tim Radvan
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
# along with this program.  If not, see {http://www.gnu.org/licenses/}.

import signal
import sys

import skip
import kurt



class ConsoleScreen(skip.Screen):
    def tick(self):
        events = []
        for event in self.interpreter.tick(events):
            if event.kind in ('say', 'think'):
                print unicode(event)
            else:
                print event

    # Script methods

    def ask(self, s, prompt):
        print "%s asks: %s" % (s.name, prompt)
        yield raw_input("? ")



if __name__ == "__main__":
    project = None
    if len(sys.argv) == 2:
        project = kurt.Project.load(sys.argv[1])

    def signal_handler(signal, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    skip.main(project, ConsoleScreen())

