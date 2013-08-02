"""A simple console-based view for a Scratch interpreter."""

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

