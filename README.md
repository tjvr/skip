# SKIP

SKIP - a Python [Scratch](http://scratch.mit.edu/) Interpreter based on [Kurt](http://github.com/blob8108/kurt).


## Status

Experimental.

Most of the 1.4 blocks are implemented, except for:

* text-related: "say", "ask", variable/list watchers
* sounds & instruments
* graphic effects other than "ghost"


## Installation

SKIP requires [Pygame](http://www.pygame.org/download.shtml) for graphics.

With a proper python environment (one which has [pip](http://www.pip-installer.org/en/latest/installing.html) available), simply run:

    $ pip install skip

Which will download SKIP and its dependencies.

Alternatively, download the compressed archive [from PyPI](http://pypi.python.org/pypi/skip), extract it, and inside it run:

    $ python setup.py install


## Usage

Run it from Terminal, passsing the path to a Scratch file:

    $ python skip/pygame_screen.py game.sb

A graphics window will open showing the stage. You can type scripts into the terminal window to execute them while the project is running.

It also includes a simple console interface. Example usage:

    $ python skip/console_screen.py
    Ctrl+D or `;` to evaluate input
    Extra commands: start, stop
    =>Sprite1
    -----
    ask "What's your name?" and wait
    say join "Hello, " join answer "!"
    ;
    ...
    Sprite1 asks: What's your name?
    ? blob
    Sprite1: say u'Hello, blob!'
    -----


## Dev

All of the graphics-related stuff is in a separate file, `pygame_screen.py`, so it should be possible to implement the interpreter for other graphics libraries (e.g. wxPython).

License: GPL v3
