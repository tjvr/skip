"""An interpreter for Scratch projects based on Kurt."""

import inspect
import math
import operator as op
import random
import time

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
        reset_timer(self)

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
        self.trigger_hats("whenGreenFlag")

    def trigger_hats(self, command, arg=None):
        for scriptable in [self.project.stage] + self.project.sprites:
            self.trigger_scriptable_hats(scriptable, command, arg)

    def trigger_scriptable_hats(self, scriptable, command, arg=None):
        for script in scriptable.scripts:
            hat = script.blocks[0]
            if hat.type.has_command(command):
                if arg is None or (hat.args and hat.args[0] == arg):
                    self.push_script(scriptable, script)

    def push_script(self, scriptable, script, callback=None):
        """Run the script and add it to the list of threads."""
        if script in self.threads:
            self.threads[script].finish()
        thread = Thread(self.run_script(scriptable, script),
                                      scriptable, callback)
        self.threads[script] = thread
        return thread

    def tick(self, events):
        """Execute one frame of the interpreter.

        Don't call more than 40 times per second.

        """
        for event in events:
            if event.kind == "key_pressed":
                assert event.value in kurt.Insert(None, "key").options()
                self.trigger_hats("whenKeyPressed", event.value)
            elif event.kind == "scriptable_clicked":
                assert isinstance(event.value, kurt.Scriptable)
                self.trigger_scriptable_hats(event.value, "whenClicked")

        remove_threads = []
        while 1:
            for (script, thread) in self.threads.items():
                modified = False
                for event in thread.tick():
                    if event.kind == "stop":
                        if event.value == "all":
                            self.stop()
                            return
                        elif event.value == "other scripts in sprite":
                            for (script, other) in self.threads.items():
                                if other.scriptable == thread.scriptable:
                                    other.finish()
                                    del self.threads[script]
                            modified = True
                            break
                        else:
                            thread.finish()
                            del self.threads[script]
                            modified = True
                            break
                    else: # Pass to Screen
                        yield event
                if modified:
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

            args = [self.evaluate(s, arg, arg_insert)
                    for (arg, arg_insert)
                    in zip(list(value.args), value.type.inserts)]
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
            if insert.shape in ("string", "readonly-menu"):
                value = unicode(value)
            if insert.kind in ("spriteOrStage", "spriteOrMouse",
                                 "stageOrThis", "spriteOnly"):
                if value not in ("mouse-pointer", "edge"):
                    value = (self.project.stage if value == "Stage"
                             else self.project.get_sprite(value))
            elif insert.kind == "var":
                if value in s.variables:
                    value = s.variables[value]
                else:
                    value = s.project.variables[value]
            elif insert.kind == "list":
                if value in s.lists:
                    value = s.lists[value]
                else:
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
            assert height is None
            ((left, bottom), (width, height)) = (left, bottom)
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

    def __setattribute__(self, name, value):
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

    def __iter__(self):
        return iter((self.left, self.bottom, self.width, self.height))


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


class Screen(object):
    def get_mouse_pos(self):
        return (0, 0)

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

def sensing(bt, method_name, after=None):
    def wrapped(s, *args):
        f = getattr(s.project.interpreter.screen, method_name)
        result = f(*args)
        if after:
            result = after(result)
        return result
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
    (x, y) = s.position
    if sprite == "mouse-pointer":
        (ox, oy) = s.project.interpreter.screen.get_mouse_pos()
    else:
        (ox, oy) = sprite.position
    dx = ox - x
    dy = oy - y
    s.direction = math.degrees(math.atan2(dx, dy))

@command("go to x: y:")
def go_to(s, x, y):
    s.position = (x, y)

@command("go to")
def go_to_sprite(s, sprite):
    if sprite == "mouse-pointer":
        s.position = s.project.interpreter.screen.get_mouse_pos()
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
    return (s.direction + 179) % 360  -  179


## Looks

@command("switch to costume")
def switch_costume(s, name):
    if isinstance(name, (int, float)):
        s.costume_index = int(round(name)) - 1
    else:
        for costume in s.costumes:
            if costume.name == name:
                s.costume = costume
                return

@command("next costume")
def next_costume(s):
    s.costume_index = (s.costume_index + 1) % len(s.costumes)

@command("costume #")
def get_costume_number(s):
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

@command("wait secs")
def wait(s, duration):
    end_time = time.time() + duration
    while time.time() <= end_time:
        yield

@command("forever")
def forever(s, body):
    while 1:
        yield s.project.interpreter.run_script(s, body)
        yield

@command("repeat")
def repeat(s, times, body):
    times = int(math.ceil(times))
    for i in range(times):
        yield s.project.interpreter.run_script(s, body)
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
        if thread in threads: # TODO zap this line
            threads.remove(thread)
    for s in [s.project.stage] + s.project.sprites:
        for script in s.scripts:
            if script.blocks[0].type.has_command("whenIReceive"):
                threads.add(s.project.interpreter.push_script(s, script,
                            callback=callback))
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
    while not s.project.interpreter.evaluate(condition):
        yield

@command("repeat until")
def repeat_until(s, condition, body):
    while not s.project.interpreter.evaluate(s, condition):
        yield s.project.interpreter.run_script(s, body)
        yield

@command("stop")
def stop_script(s, which):
    yield ScriptEvent(s, 'stop', which)

## Sensing

def matmult(*args):
    def mult(a, b):
        # http://stackoverflow.com/questions/10508021
        zip_b = zip(*b)
        return [[sum(ele_a*ele_b for ele_a, ele_b in zip(row_a, col_b))
                 for col_b in zip_b] for row_a in a]
    return reduce(mult, args)

def transformation_matrix(x, y, sc, cx, cy, theta):
    sina = math.sin(a)
    cosa = math.cos(a)

    A = matmult([[1, 0, x],  # translate
                 [0, 1, y],
                 [0, 0, 1]],
                [[1, 0, cx],
                 [0, 1, cy],
                 [0, 0, 1]],
                [[sc, 0, 0], # scale
                 [0, sc, 0],
                 [0, 0, 1]],
                [[cosa, sina,


def bounds(s):
    (x, y) = s.position
    (w, h) = s.costume.size
    scale = s.size / 100

    # resize and transform
    tlx = x - s.costume.rotation_center[0] * scale
    tly = y + s.costume.rotation_center[1] * scale
    w *= scale
    h *= scale
    rect = Rect(tlx, tly, w, h)

    # rotate
    if s.rotation_style == "normal":
        # rect : has four corners.
        # (x, y) : the centre of rotation.

        a = math.radians(s.direction - 90)

        rotate = lambda (x, y): (x + (cx - x)*cosa + (cy - y)*sina,
                                 y - (cx-x)*sina + (cy-y)*cosa)

        xs = []
        ys = []
        for (cx, cy) in (rect.topleft, rect.topright, rect.bottomleft,
                         rect.bottomright):
            (rot_cx, rot_cy) = rotate((cx, cy))
            xs.append(rot_cx)
            ys.append(rot_cy)

        left = min(xs)
        right = max(xs)
        bottom = min(ys)
        top = max(ys)

        bottomleft = (left, bottom)

        rot_w = right - left
        rot_h = top - bottom

        #assert rot_w == h * cosa  +  w * sina
        #assert rot_h == h * sina  +  w * cosa

        rect = Rect(bottomleft, (rot_w, rot_h))

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

sensing("mouse x", "get_mouse_pos", lambda (x, y): x)
sensing("mouse y", "get_mouse_pos", lambda (x, y): y)
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
    attr_functions = {
        'x position': get_x,
        'y position': get_y,
        'direction': get_direction,
        'costume #': get_costume_number,
        'size': get_size,
        'volume': get_volume,
    }
    f = attr_functions[name]
    return f(sprite)

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
        'abs': abs,
        'sqrt': math.sqrt,
        'sin': lambda deg: math.sin(math.radians(deg)),
        'cos': lambda deg: math.cos(math.radians(deg)),
        'tan': lambda deg: math.tan(math.radians(deg)),
        'asin': lambda n: math.degrees(math.asin(n)),
        'acos': lambda n: math.degrees(math.acos(n)),
        'atan': lambda n: math.degrees(math.atan(n)),
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
    variable.value = float(variable.value) + float(delta)

@command("show variable")
def show_variable(s, variable):
    variable.watcher.is_visible = True

@command("hide variable")
def hide_variable(s, variable):
    variable.watcher.is_visible = False

## Lists

@command("list")
def get_list(s, list_):
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



#-- REPL --#

class ConsoleScreen(Screen):
    def set_project(self, project):
        self.project = project
        self.interpreter = Interpreter(project).bind(self)

    def tick(self):
        events = []
        for event in self.interpreter.tick(events):
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

    # Script methods

    def ask(self, s, prompt):
        print "%s asks: %s" % (s.name, prompt)
        yield raw_input("? ")


def main(sprite=None):
    if sprite is None:
        project = kurt.Project()
        sprite = kurt.Sprite(project, "Sprite1")
        project.sprites = [sprite]
    else:
        project = sprite.project

    screen = ConsoleScreen()
    screen.set_project(project)

    interpreter = sprite.project.interpreter
    screen = interpreter.screen
    interpreter.start()

    print "Semicolon ';' terminates input"
    while 1:
        text = line = ""
        while not line.endswith(";"):
            line = raw_input("> ")
            text += line + "\n"
        text = text.rstrip().rstrip(";")
        script = kurt.text.parse_expression(text.strip(), sprite)
        if isinstance(script, kurt.Block) and script.type.shape in ("reporter",
                "boolean"):
            print repr(interpreter.evaluate(sprite, script))
        else:
            if isinstance(script, kurt.Block):
                script = [script]
            script = kurt.Script(script)
            interpreter.push_script(sprite, script)
            while interpreter.threads:
                screen.tick()

