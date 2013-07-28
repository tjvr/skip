"""An interpreter for Scratch projects based on Kurt."""

import math
import time
import operator as op
import inspect
import random

import kurt



#-- Interpreter --#

class Thread(object):
    def __init__(self, generator, scriptable, callback):
        self.generator = generator
        self.scriptable = scriptable
        self.callback = callback

    def tick(self):
        try:
            event = self.generator.next()
            while event:
                assert isinstance(event, ScriptEvent)
                yield event
                event = self.generator.next()
        except StopIteration:
            yield ScriptEvent(self.scriptable, "stop")

    def finish(self):
        if self.callback:
            self.callback(self)


class Interpreter(object):
    COMMANDS = {}

    def __init__(self, project):
        self.project = project
        project.interpreter = self
        for scriptable in [self.project.stage] + self.project.sprites:
            self.augment(scriptable)
        self.stop()

    def bind(self, screen):
        self.screen = screen
        return self

    def augment(self, scriptable):
        scriptable.graphic_effects = {
            'brightness': 0,
            'color': 0,
            'fisheye': 0,
            'ghost': 0,
            'mosaic': 0,
            'pixelate': 0,
            'whirl': 0,
        }
        scriptable.instrument = 1

        if isinstance(scriptable, kurt.Sprite):
            scriptable.pen_size = 1
            scriptable.pen_color = kurt.Color("#00f")
            scriptable.pen_hue = 0   # TODO ?
            scriptable.pen_shade = 0 # TODO ?

    # Threads

    def start(self):
        """Trigger green flag scripts."""
        self.stop()
        reset_timer(self)
        for scriptable in [self.project.stage] + self.project.sprites:
            for script in scriptable.scripts:
                if script.blocks[0].type.has_command("whenGreenFlag"):
                    self.push_script(scriptable, script)

    def push_script(self, scriptable, script, callback=None):
        """Run the script and add it to the list of threads."""
        if script in self.threads:
            self.threads[script].finish()
        thread = Thread(self.run_script(scriptable, script),
                                      scriptable, callback)
        self.threads[script] = thread
        return thread

    def tick(self):
        """Execute one frame of the interpreter.

        Don't call more than 40 times per second.

        """
        remove_threads = []
        while 1:
            for (script, thread) in self.threads.items():
                remove = False
                for event in thread.tick():
                    if event.kind == "stop":
                        if event.value == "all":
                            self.stop()
                            return
                        elif event.value == "other scripts in sprite":
                            pass # TODO
                        else:
                            thread.finish()
                            remove = True
                            break
                    else: # Pass to Screen
                        yield event
                if remove:
                    del self.threads[script]
                    break
            else:
                break

    def stop(self):
        """Stop running threads."""
        self.threads = {}
        self.answer = ""
        self.ask_lock = False

    # Scripts

    def run_script(self, s, script):
        for block in script:
            for x in self.evaluate(s, block):
                yield x

    def evaluate(self, s, value, insert=None):
        """Expression evaluator.

        * For expressions, returns the value of the expression.

        * For Blocks, returns a generator (or the empty list []).

        """
        assert not isinstance(value, kurt.Script)

        if insert and insert.unevaluated:
            return value

        if isinstance(value, kurt.Block):
            if value.type.shape == "hat":
                return []

            if value.type not in self.COMMANDS:
                if hasattr(value.type, '_workaround'):
                    value = value.type._workaround(value)
                    if not value:
                        raise KeyError, value.type
                else:
                    raise KeyError, value.type

            f = self.COMMANDS[value.type]

            args = [self.evaluate(s, arg, insert)
                    for (arg, insert) in zip(value.args, value.type.inserts)]
            value = f(s, *args)

            def flatten_generators(gen):
                for item in gen:
                    if inspect.isgenerator(item):
                        for x in flatten_generators(item):
                            yield x
                    else:
                        yield item
            if inspect.isgenerator(value):
                value = flatten_generators(value)

            if value is None:
                value = []

        if insert:
            if isinstance(value, basestring):
                try:
                    value = float(value)
                    if value == int(value):
                        value = int(value)
                except (TypeError, ValueError):
                    pass

            if insert.kind in ("spriteOrStage", "spriteOrMouse",
                                 "stageOrThis", "spriteOnly"):
                if value not in ("mouse-pointer", "edge"):
                    value = (self.project.stage if value == "Stage"
                                                else project.get_sprite(value))
            elif insert.kind == "var":
                if value in s.variables:
                    value = s.variables[value]
                else:
                    if value not in s.project.variables:
                        s.project.variables[value] = kurt.Variable()
                    value = s.project.variables[value]
            elif insert.kind == "list":
                if value in s.lists:
                    value = s.lists[value]
                else:
                    if value not in s.project.lists:
                        s.project.lists[value] = kurt.Variable()
                    value = s.project.lists[value]

        return value



#-- Screen --#

class Rect(object):
    """An area of screen with both size and position.

    Usage:

        Rect(left, bottom, width, height)
        Rect((left, bottom), (width, height))
        Rect((left, bottom, width, height))

    """
    # TODO optimize
    def __init__(self, left, bottom=None, width=None, height=None):
        if bottom is None:
            (left, bottom, width, height) = left
        elif width is None:
            assert height is not None
            ((left, bottom), (width, height)) = bottom
        self.bottomleft = (left, bottom)
        self.size = (width, height)

    def __getattr__(self, name):
        if name == 'width':
            return self.size[0]
        elif name == 'height':
            return self.size[1]
        elif name == 'left' or name == 'x':
            return self.bottomleft[0]
        elif name == 'right':
            return self.left + self.width
        elif name == 'bottom' or name == 'y':
            return self.bottomleft[1]
        elif name == 'top':
            return self.bottom + self.height
        elif name == 'bottomright':
            return (self.right, self.bottom)
        elif name == 'topleft':
            return (self.left, self.top)
        elif name == 'topright':
            return (self.right, self.top)
        elif name == 'centerx':
            return self.left + self.width / 2
        elif name == 'centery':
            return self.bottom + self.height / 2
        elif name == 'center':
            return (self.centerx, self.centery)
        else:
            raise AttributeError('%r has no attribute %r' % (type(self), name))

    def __setattr__(self, name, value):
        if name == 'width':
            self.size[0] = value
        elif name == 'height':
            self.size[1] = value
        elif name == 'left' or name == 'x':
            self.bottomleft[0] = value
        elif name == 'right':
            self.left = value - self.width
        elif name == 'bottom' or name == 'y':
            self.bottomleft[1] = value
        elif name == 'top':
            self.bottom = value - self.height
        elif name == 'bottomright':
            (self.right, self.bottom) = value
        elif name == 'topleft':
            (self.left, self.top) = value
        elif name == 'topright':
            (self.right, self.top) = value
        elif name == 'centerx':
            self.left = value - self.width / 2
        elif name == 'centery':
            self.bottom = value - self.height / 2
        elif name == 'center':
            (self.centerx, self.centery) = value
        else:
            raise AttributeError('%r has no attribute %r' % (type(self), name))


class ScriptEvent(object):
    """Yielded from a block function to the Interpreter.

    May then be passed to the Screen.

    """
    def __init__(self, scriptable, kind, value=None):
        self.scriptable = scriptable
        self.kind = kind
        self.value = value

    def __repr__(self):
        r = "ScriptEvent(%r, %r" % (self.scriptable, self.kind)
        if self.value is not None:
            r += ", %r" % self.value
        r += ")"
        return r

    def __unicode__(self):
        return "%s: %s %r" % (self.scriptable.name, self.kind, self.value)


class ScreenEvent(object):
    """An event passed from Screen to the Interpreter."""
    def __init__(self, kind, value=None):
        self.kind = kind
        self.value = value

    def __repr__(self):
        r = "ScreenEvent(%r" % self.kind
        if self.value is not None:
            r += ", %r" % self.value
        r += ")"
        return r


class IScreen(object):
    def get_mouse_x(self):
        return 0

    def get_mouse_y(self):
        return 0

    def is_mouse_down(self):
        return False

    def is_key_pressed(self, name):
        return False

    def touching_sprite(self, s, sprite):
        return False

    def touching_color(self, s, color):
        return False

    def touching_color_over(self, s, color, over):
        return False

    def ask(self, s, prompt):
        # sync: yield while waiting for answer.
        while 0:
            yield
        yield ""

    def play_sound(self, s, sound):
        pass

    def play_sound_until_done(self, s, sound):
        self.play_sound(s, sound)
        while 0: # sync: yield while playing
            yield

    def stop_sounds(self, s):
        pass


class ConsoleScreen(IScreen):
    def set_project(self, project):
        self.project = project
        self.interpreter = Interpreter(project).bind(self)

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

    def ask(self, s, prompt):
        print "%s asks: %s" % (s.name, prompt)
        yield raw_input("? ")



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

def sensing(bt, method_name):
    def wrapped(s, *args):
        f = getattr(s.project.interpreter.screen, method_name)
        return f(*args)
    return command(bt)(wrapped)

## Motion

@command("move steps")
def move(s, distance):
    radians = math.radians(s.direction)
    (x, y) = s.position
    x += math.sin(radians) * distance
    y += math.cos(radians) * distance
    s.position = (x, y)

@command("turn @turnLeft degrees")
def turn_left(s, angle):
    s.direction -= angle

@command("turn @turnRight degrees")
def turn_right(s, angle):
    s.direction += angle

@command("point in direction")
def set_direction(s, direction):
    s.direction = direction

@command("point towards")
def point_towards(s, sprite):
    dx = sprite.pos[0] - s.pos[0]
    dy = sprite.pos[1] - s.pos[1]
    s.direction = math.degrees(math.atan2(dx, dy))

@command("go to x: y:")
def go_to(s, x, y):
    s.position = (x, y)

@command("go to")
def go_to_sprite(s, sprite):
    if sprite == "mouse":
        pass # TODO
    else:
        s.position = sprite.position

@command("glide secs to x: y:")
def glide_to_for_secs(s, duration, end_x, end_y):
    (start_x, start_y) = s.position
    now = time.time()
    end_time = now + secs
    while now <= end_time:
        t = float(now - start_time) / duration
        s.position = (start_x * (1 - t)  +  end_x * t,
                      start_y * (1 - t)  +  end_y * t)
        yield
        now = time.time()

@command("change x by")
def change_x(s, delta):
    (x, y) = s.position
    x += delta
    s.position = (x, y)

@command("set x to")
def set_x(s, value):
    (x, y) = s.position
    s.position = (value, y)

@command("change y by")
def change_y(s, delta):
    (x, y) = s.position
    y += delta
    s.position = (x, y)

@command("set y to")
def set_y(s, value):
    (x, y) = s.position
    s.position = (x, value)

# TODO if on edge, bounce

@command("x position")
def get_x(s):
    return s.position[0]

@command("y position")
def get_y(s):
    return s.position[1]

@command("direction")
def get_direction(s):
    return s.direction


## Looks

@command("switch to costume")
def switch_costume(s, name):
    if isinstance(name, (int, float)):
        s.costume_index = round(name) - 1
    else:
        for costume in s.costumes:
            if costume.name == name:
                s.costume = costume
                return

@command("next costume")
def next_costume(s):
    s.costume_index = (s.costume_index + 1) % len(s.costumes)

@command("costume #")
def costume_number(s):
    return s.costume_index + 1

@command("say")
def say(s, message):
    yield ScriptEvent(s, "say", message)

@command("say for secs")
def say_for_secs(s, message, secs):
    yield say(s, message)
    yield wait(s, secs)
    yield say(s, None)

@command("think")
def think(s, message):
    yield ScriptEvent(s, "think", message)

@command("think for secs")
def think_for_secs(s, message, secs):
    yield think(s, message)
    yield wait(s, secs)
    yield think(s, None)

@command("change effect by")
def change_effect(s, effect, delta):
    s.graphic_effects[effect] += delta

@command("set effect to")
def set_effect(s, effect, value):
    s.graphic_effects[effect] = value

@command("clear graphic effects")
def clear_effects(s):
    for effect in s.graphic_effects:
        s.graphic_effects[effect] = 0

@command("change size by")
def change_size(s, delta):
    s.size += delta

@command("set size to %")
def set_size(s, value):
    s.size = value

@command("size")
def get_size(s):
    return s.size

@command("show")
def show(s):
    s.is_visible = True

@command("hide")
def hide(s):
    s.is_visible = False

@command("go to front")
def go_to_front(s):
    # TODO Objects which appear later in the array are on top of those which
    # appear earlier.
    s.project.actors.remove(s)
    s.project.actors.append(s)

@command("go back layers")
def go_back_by(s, n):
    index = s.project.actors.index(s)
    s.project.actors.remove(s)
    s.project.actors.insert(max(0, index - n), s)

@command("switch backdrop to")
def switch_backdrop(s, name):
    return switch_costume(s.project.stage, name)

@command("next backdrop")
def next_backdrop(s):
    return next_costume(s.project.stage)

@command("background #")
def background_number(s):
    return costume_number(s.project.stage)

## Sound

@command("play sound")
def play_sound(s, sound):
    s.project.interpreter.screen.play_sound(s, sound)

@command("play sound until done")
def play_sound_until_done(s, sound):
    return s.project.interpreter.screen.play_sound_until_done(s, sound)

@command("stop all sounds")
def stop_sounds(s):
    s.project.interpreter.screen.stop_sounds()

def beat_seconds(s, beats):
    seconds_per_beat = 60 / s.project.tempo
    return beats * seconds_per_beat

@command("rest for beats")
def rest_beats(s, beats):
    return wait(beat_seconds(beats))

@command("play drum for beats")
def play_drum(s, drum, beats):
    s.project.interpreter.screen.play_drum(drum, beat_seconds(beats))

@command("play note for beats")
def play_note(s, note, beats):
    s.project.interpreter.screen.play_note(note, beat_seconds(beats))

@command("set instrument to")
def set_instrument(s, value):
    s.instrument = value

@command("change volume by")
def change_volume(s, delta):
    s.volume += delta

@command("set volume to")
def set_volume(s, value):
    s.volume = value

@command("volume")
def get_volume(s):
    return s.volume

@command("change tempo by")
def change_tempo(s, delta):
    s.project.tempo += delta

@command("set tempo to bpm")
def set_tempo(s, value):
    s.project.tempo = value

@command("tempo")
def get_tempo(s):
    return s.project.tempo

## Pen

@command("clear")
def clear(s):
    yield ScriptEvent(s, "clear")

@command("pen down")
def pen_down(s):
    s.is_pen_down = True

@command("pen up")
def pen_up(s):
    s.is_pen_up = False

@command("penColor:")
def set_pen_color(s, color):
    s.pen_color = color

@command("changePenHueBy:")
def change_pen_hue(s, delta):
    s.pen_hue += delta

@command("setPenHueTo:")
def set_pen_hue(s, value):
    s.pen_hue = value

@command("change pen shade by")
def change_pen_shade(s, delta):
    s.pen_shade += delta

@command("set pen shade to")
def set_pen_shade(s, value):
    s.pen_shade = value

@command("change pen size by")
def change_pen_size(s, delta):
    s.pen_size += delta

@command("set pen size to")
def set_pen_size(s, value):
    s.pen_size = value

@command("stamp")
def stamp(s):
    yield ScriptEvent(s, "stamp")

## Control

# TODO when key pressed
# TODO when clicked

@command("wait secs")
def wait(s, duration):
    end_time = time.time() + duration
    while time.time() <= end_time:
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
                s.project.interpreter.push_script(s, script)

@command("broadcast and wait")
def broadcast_and_wait(s, message):
    threads = set()
    def callback(thread):
        print 'remove', thread
        threads.remove(thread)
    for s in [s.project.stage] + s.project.sprites:
        for script in s.scripts:
            if script.blocks[0].type.has_command("whenIReceive"):
                threads.add(s.project.interpreter.push_script(s, script,
                            callback=callback))
    print threads
    while threads:
        yield


@command("if")
def if_(s, condition, body):
    if condition:
        yield s.project.interpreter.run_script(s, body)

@command("if else")
def if_else(s, condition, body, other_body):
    yield s.project.interpreter.run_script(s,
                                           body if condition else other_body)

@command("wait until")
def wait_until(s, condition):
    while not evaluate(condition):
        yield

@command("repeat until")
def wait_until(s, condition):
    while not evaluate(condition):
        yield s.project.interpreter.run_script(s, blocks)
        yield

@command("stop")
def stop_script(s, which):
    yield ScriptEvent(s, 'stop', which)

## Sensing

def bounds(s):
    (x, y) = s.position
    x -= s.costume.rotation_center[0]
    y += s.costume.rotation_center[1]
    rect = Rect((x, y), s.costume.size)
    # TODO rotate
    # TODO scale
    return rect

@command("touching")
def touching_sprite(s, sprite):
    rect = bounds(s)
    if sprite == "edge":
        return (rect.left < -240 or rect.right > 240 or rect.top > 180 or
                rect.bottom < -180)
    else:
        return s.project.interpreter.screen.touching_sprite(s, sprite)

@command("touching color")
def touching_color(s, color):
    return s.project.interpreter.screen.touching_color(s, color)

@command("color is touching")
def touching_color(s, color, over):
    return s.project.interpreter.screen.touching_color_over(s, color, over)

@command("ask and wait")
def ask(s, prompt):
    while s.project.interpreter.ask_lock:
        yield
    s.project.interpreter.ask_lock = True
    for answer in s.project.interpreter.screen.ask(s, prompt):
        if answer:
            s.project.interpreter.answer = answer
            break
        yield
    s.project.interpreter.ask_lock = False

@command("answer")
def answer(s):
    return s.project.interpreter.answer

sensing("mouse x", "get_mouse_x")
sensing("mouse y", "get_mouse_y")
sensing("mouse down?", "is_mouse_down")
sensing("key pressed?", "is_key_pressed")

@command("distance to")
def distance_to(s, sprite):
    (x, y) = self.pos
    (ox, oy) = sprite.pos
    return math.sqrt((x - ox) ** 2 + (y - oy) ** 2)

@command("reset timer")
def reset_timer(s):
    s.project.interpreter.timer_start = time.time()

@command("timer")
def timer(s):
    return time.time() - s.project.interpreter.timer_start

@command("getAttribute:of:")
def attribute_of(s, name, sprite):
    attributes = {
        'x position': sprite.pos[0],
        'y position': sprite.pos[1],
        'direction': sprite.direction,
        'costume #': sprite.costume_index + 1,
        'size': sprite.size,
        'volume': sprite.volume,
    }
    return attributes[name]

@command("loudness")
def loudness(s):
    return 20

## Operators

operator("+", op.add)
operator("-", op.sub)
operator("*", op.mul)
operator("/", op.truediv)

operator("pick random to", random.randint)

operator("=", op.eq)
operator("<", op.lt)
operator(">", op.gt)

operator("and", op.and_)
operator("or", op.or_)
operator("not", op.not_)

operator("join", op.add)
operator("letter of", lambda i, string: string[i - 1])
operator("stringLength:", len)

operator("mod", op.mod)
operator("round", round)

@command("computeFunction:of:")
def math_function(s, name, arg):
    functions = {
        'abs': math.abs,
        'sqrt': math.sqrt,
        'sin': lambda deg: math.sin(math.radians(deg)),
        'cos': lambda deg: math.cos(math.radians(deg)),
        'tan': lambda deg: math.tan(math.radians(deg)),
        'asin': lambda n: math.asin(math.degrees(n)),
        'acos': lambda n: math.acos(math.degrees(n)),
        'atan': lambda n: math.atan(math.degrees(n)),
        'log': lambda n: math.log(n, 10),
        'ln': math.log,
        'e ^': lambda n: math.e ** n,
        '10 ^': lambda n: 10 ** n,
    }
    f = functions[name]
    return f(arg)

## Variables

@command("var")
def get_variable(s, variable):
    return variable.value

@command("set to")
def set_variable(s, variable, value):
    variable.value = value

@command("change by")
def change_variable(s, variable, delta):
    variable.value += delta

@command("show variable")
def show_variable(s, variable):
    variable.watcher.is_visible = True

@command("hide variable")
def hide_variable(s, variable):
    variable.watcher.is_visible = False

## Lists

@command("list")
def get_variable(s, list_):
    return " ".join(list_.items) # TODO correct behaviour

@command("add to")
def add_item(s, item, list_):
    list_.items.append(item)

@command("delete of")
def delete_item(s, index, list_):
    if index == 'all':
        list_.items = []
    else:
        if index == 'last':
            index = 0
        list_.items.pop(index - 1)

@command("insert at of")
def insert_item_at(s, item, index, list_):
    if index == 'last':
        list_.items.append(item)
    else:
        l = list_
        if index == 'any':
            index = random.randint(1, len(l.items))
        l.items.insert(index - 1, item)

@command("replace item of with")
def replace_item_with(s, index, list_, item):
    if index == 'last':
        index = 0
    elif index == 'any':
        index = random.randint(1, len(l.items))
    list_.items[index - 1] = item

operator("item of", lambda i, list_: list_.items[i - 1])
operator("lineCountOfList:", lambda list_: len(list_.items))
operator("contains", lambda list_, item: item in list_.items)



#-- Test --#

s14_blocks = set(b for b in kurt.plugin.Kurt.blocks
                 if b.has_translation("scratch14")
                    and 'obsolete' not in b.translate("scratch14").category
                    and 'motor' not in b.text
                    and 'sensor' not in b.text
                    and not b._workaround
                    and not b.shape == "hat"
                )

print "%i blocks done, %i to go" % (len(Interpreter.COMMANDS),
        len(s14_blocks) - len(Interpreter.COMMANDS))
blocks_todo = s14_blocks - set(Interpreter.COMMANDS)
def suggest():
    print "Next block: %s" % random.choice(list(blocks_todo))
suggest()
def suggest_all():
    return sorted(blocks_todo, key=lambda b: b.text)


p = kurt.Project()
p.sprites = [kurt.Sprite(p, "cat")]
p.stage.parse("""
when gf clicked
forever
    say "I'm alive!"
    wait 0.5 secs
end
""")
p.stage.parse("""
when gf clicked
say "We need your name."
ask "What is your name?" and wait
say join "Hello, " answer
""")

sprite = kurt.Sprite(p, 'Sprite1')
p.sprites.append(sprite)
parsec = lambda text: kurt.text.parse(text, sprite)
def ev(text):
    project = p.copy()
    screen = ConsoleScreen()
    screen.set_project(project)
    elda = screen.interpreter
    elda.start()
    elda.tick()
    sprite = project.sprites[0]
    script = kurt.text.parse_expression(text, sprite)
    return elda.evaluate(sprite, script)

