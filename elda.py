"""An interpreter for Scratch projects based on Kurt."""

import math
import time
import operator as op

import kurt



#-- Interpreter --#

class Interpreter(object):
    COMMANDS = {}

    def __init__(self, project):
        self.project = project
        self.stop()

    def start(self):
        """Trigger green flag scripts."""
        self.stop()
        self.start_time = None
        for scriptable in [self.project.stage] + self.project.sprites:
            for script in scriptable.scripts:
                if script.blocks[0].type.has_command("whenGreenFlag"):
                    push_script(scriptable, script[1:])

    def tick(self):
        """Execute one frame of the interpreter.

        Don't call more than 40 times per second.

        """
        self.start_time = self.start_time or time.time()
        self.project.timer = time.time() - self.start_time
        for scriptable in [self.project.stage] + self.project.sprites:
            for thread in scriptable.threads:
                try:
                    thread.next()
                except StopIteration:
                    scriptable.threads.remove(thread)
 
    def stop(self):
        """Stop running threads."""
        for s in [self.project.stage] + self.project.sprites:
            s.threads = []



#-- Scripts --#

def evaluate(s, value, insert=None):
    assert not isinstance(value, kurt.Script)
    if isinstance(value, kurt.Block):
        f = Interpreter.COMMANDS[value.type]
        args = [evaluate(s, arg, insert)
                for (arg, insert) in zip(value.args, value.type.inserts)]
        result = f(s, *args)
        if result is None:
            result = []
        return result
    else: # float, unicode, list
        return value

def push_script(s, script):
    if script not in s.threads:
        s.threads.append(run_script(s, script))

def run_script(s, script):
    for block in script:
        for x in evaluate(s, block):
            yield

def run(p):
    elda = Interpreter(p)
    elda.start()
    while 1:
        elda.tick(time.time())



#-- Commands --#

# def block(s, *args):
# :param s: the Scriptable the block is evaluated on

def command(bt):
    def decorator(func, bt=bt):
        bt = kurt.BlockType.get(bt)
        Interpreter.COMMANDS[bt] = func
        return func
    return decorator

def operator(bt, func):
    def wrapped(s, *args):
        return func(*args)
    return command(bt)(wrapped)

operator("+", op.add)
operator("-", op.sub)
operator("*", op.mul)
operator("/", op.truediv)
operator("mod", op.mod)

operator("and", op.and_)
operator("or", op.or_)
operator("not", op.not_)

operator("=", op.eq)
operator("<", op.lt)
operator(">", op.gt)

@command("say")
def say(s, message):
    print message

@command("wait secs")
def wait(s, secs):
    start = time.time()
    while time.time() <= start + secs:
        yield

@command("forever")
def forever(s, blocks):
    while 1:
        for x in run_script(s, blocks):
            yield
        yield

@command("repeat")
def repeat(s, times, blocks):
    times = int(math.ceil(times))
    for i in range(times):
        for x in run_script(s, blocks):
            yield
        yield

@command("broadcast")
def broadcast(s, message):
    for s in [scriptable.project.stage] + scriptable.project.sprites:
        for script in s.scripts:
            if script.blocks[0].type.has_command("whenIReceive"):
                push_script(s, script[1:])

@command("timer")
def timer(s):
    return s.project.timer

#-- Test --#

p = kurt.Project()
p.stage.scripts = [
    kurt.Script([
        kurt.Block("when I receive", "begin"),
        kurt.Block("forever", [
            kurt.Block("say", "hi"),
            kurt.Block("wait secs", 1),
        ]),
    ]),
    kurt.Script([
        kurt.Block("when I receive", "begin"),
        kurt.Block("forever", [
            kurt.Block("wait secs", 1),
            kurt.Block("say", "boo"),
        ]),
    ]),
    kurt.Script([
        kurt.Block("when @greenFlag clicked"),
        kurt.Block("repeat", 2, [
            kurt.Block("say", "poo"),
            kurt.Block("wait secs", 1),
        ]),
        kurt.Block("broadcast", "begin"),
        kurt.Block("say", "before"),
    ]),
]

sprite = kurt.Sprite(p, 'Sprite1')
p.sprites.append(sprite)
parsec = lambda text: kurt.text.parse(text, sprite)
#def ev(text):
#    project = p.copy()
#    elda = Interpreter(p)
#    elda.start()
#    project.sprites[0]
#
#ev = lambda text: evaluate(sprite, parsec(text)[0])
#
