"""An interpreter for Scratch projects based on Kurt."""

import math
import time
import operator as op
import inspect
import random

import kurt



#-- Interpreter --#

class Interpreter(object):
    COMMANDS = {}

    def __init__(self, project):
        self.project = project
        project.interpreter = self
        for scriptable in [self.project.stage] + self.project.sprites:
            self.augment(scriptable)
        self.stop()

    def augment(self, scriptable):
        if isinstance(scriptable, kurt.Sprite):
            scriptable.speech_bubble = None
            scriptable.last_speech_bubble = None

    # Threads

    def start(self):
        """Trigger green flag scripts."""
        self.stop()
        reset_timer(self)
        for scriptable in [self.project.stage] + self.project.sprites:
            for script in scriptable.scripts:
                if script.blocks[0].type.has_command("whenGreenFlag"):
                    self.push_script(scriptable, script[1:])

    def push_script(self, s, script):
        if script not in self.threads:
            self.threads.append(self.run_script(s, script))

    def tick(self):
        """Execute one frame of the interpreter.

        Don't call more than 40 times per second.

        """
        for thread in self.threads:
            try:
                event = True
                while event:
                    event = thread.next()
                    if event:
                        yield event
            except StopIteration:
                self.threads.remove(thread)

    def stop(self):
        """Stop running threads."""
        self.threads = []

    # Scripts

    def run_script(self, s, script):
        for block in script:
            for x in self.evaluate(s, block):
                yield x

    def evaluate(self, s, value, insert=None):
        assert not isinstance(value, kurt.Script)
        if isinstance(value, kurt.Block):
            f = Interpreter.COMMANDS[value.type]
            args = [self.evaluate(s, arg, insert)
                    for (arg, insert) in zip(value.args, value.type.inserts)]
            result = f(s, *args)

            def flatten_generators(gen):
                for item in gen:
                    if inspect.isgenerator(item):
                        for x in flatten_generators(item):
                            yield x
                    else:
                        yield item
            if inspect.isgenerator(result):
                result = flatten_generators(result)

            if result is None:
                result = []
            return result
        else: # float, unicode, list
            return value



#-- Screen --#

class Event(object):
    def __init__(self, scriptable, kind, value):
        self.scriptable = scriptable
        self.kind = kind
        self.value = value

    def __repr__(self):
        return "Event(%r, %r, %r)" % (self.scriptable, self.kind, self.value)

    def __unicode__(self):
        return "%s: %s %r" % (self.scriptable.name, self.kind, self.value)

class IScreen(object):
    pass

class ConsoleScreen(object):
    def set_project(self, project):
        self.project = project
        self.interpreter = Interpreter(project)

    def tick(self):
        for event in self.interpreter.tick():
            if event.kind in ('say', 'think'):
                print unicode(event)
            else:
                print event

    @classmethod
    def run(cls, project):
        """Run the project until all the scripts die."""
        scr = cls()
        scr.set_project(project)
        scr.interpreter.start()
        while scr.interpreter.threads:
            scr.tick()



#-- Commands --#

# def block(s, *args):
# :param s: the Scriptable the block is evaluated on
# Must be return an iterable (ie. a generator) or None

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
    yield Event(s, "say", message)

@command("say for secs")
def say_for_secs(s, message, secs):
    yield say(s, message)
    yield wait(s, secs)
    yield say(s, None)

@command("think")
def think(s, message):
    yield Event(s, "think", message)

@command("think for secs")
def think_for_secs(s, message, secs):
    yield think(s, message)
    yield wait(s, secs)
    yield think(s, None)

@command("wait secs")
def wait(s, secs):
    start = time.time()
    while time.time() <= start + secs:
        yield

@command("forever")
def forever(s, blocks):
    while 1:
        yield s.project.interpreter.run_script(s, blocks)
        yield

@command("repeat")
def repeat(s, times, blocks):
    times = int(math.ceil(times))
    for i in range(times):
        yield s.project.interpreter.run_script(s, blocks)
        yield

@command("broadcast")
def broadcast(s, message):
    for s in [s.project.stage] + s.project.sprites:
        for script in s.scripts:
            if script.blocks[0].type.has_command("whenIReceive"):
                s.project.interpreter.push_script(s, script[1:])

@command("reset timer")
def reset_timer(s):
    s.project.interpreter.timer_start = time.time()

@command("timer")
def timer(s):
    return time.time() - s.project.interpreter.timer_start

@command("if")
def if_(s, condition, body):
    if condition:
        yield run_script(body)

@command("if else")
def if_else(s, condition, body, other_body):
    yield run_script(body if condition else other_body)



#-- Test --#

blocks_todo = set()
for block in kurt.plugin.Kurt.get_plugin('scratch14').blocks:
#for block in kurt.plugin.Kurt.blocks:
#    for translation in block.translations:
#        if 'obsolete' in block.translate().category:
    if block and 'obsolete' not in block.category:
#        break
#    else:
        blocks_todo.add(block)
print "Done %i out of %i blocks" % (len(Interpreter.COMMANDS),
        len(blocks_todo))
print "Next block: %s" % random.choice(list(blocks_todo))


p = kurt.Project()
p.stage.parse("""
when gf clicked
repeat 10
    say 'hi'
end
""")
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
        kurt.Block("when I receive", "begin"),
        kurt.Block("think for secs", "Heya", 5),
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
def ev(text):
    project = p.copy()
    elda = Interpreter(p)
    elda.start()
    elda.tick()
    sprite = p.sprites[0]
    script = kurt.text.parse_expression(text, sprite)
    return elda.evaluate(sprite, script)

