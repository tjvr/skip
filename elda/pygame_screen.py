"""A Pygame-based view for a Scratch interpreter."""

import select
import sys

import pygame
import pygame

import elda
from elda import Rect, ScreenEvent
import kurt



class PygameScreen(elda.Screen):
    CAPTION = "elda"
    KEYS_BY_NAME = {}

    def __init__(self):
        self.surface = pygame.display.set_mode(kurt.Stage.SIZE)
        pygame.display.set_caption(self.CAPTION)

        self.pen_surface = pygame.Surface(kurt.Stage.SIZE).convert_alpha()
        self.clear()

        self.clock = pygame.time.Clock()

        self.running = True
        self.surfaces = {}

        for constant in dir(pygame):
            if constant.startswith("K_"):
                key = eval("pygame."+constant)
                name = pygame.key.name(key)
                self.KEYS_BY_NAME[name] = key

    def set_project(self, project):
        self.project = project
        self.interpreter = elda.Interpreter(project).bind(self)
        if project.name:
            pygame.display.set_caption(project.name + " : " + self.CAPTION)
        else:
            pygame.display.set_caption(self.CAPTION)
        for scriptable in [project.stage] + project.sprites:
            for costume in scriptable.costumes:
                p_i = costume.image.pil_image
                assert p_i.mode in ("RGB", "RGBA")
                self.surfaces[costume.image] = pygame.image.fromstring(
                        p_i.tostring(), p_i.size, p_i.mode).convert_alpha()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q:
                    self.running = False
                else:
                    name = pygame.key.name(event.key)
                    if name in kurt.Insert(None, "key").options():
                        yield ScreenEvent("key_pressed", name)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 0:
                    yield ScreenEvent("click")

    def tick(self):
        self.clock.tick(40)

        events = list(self.handle_events())
        for event in self.interpreter.tick(events):
            if event.kind == "clear":
                self.clear()
            elif event.kind == "stamp":
                self.stamp(event.scriptable)
            elif event.kind in ("say", "think"):
                print "::", unicode(event)
            else:
                print "::", event

        self.draw_sprite(self.project.stage, self.surface)
        self.surface.blit(self.pen_surface, (0, 0))
        for actor in self.project.actors:
            if isinstance(actor, kurt.Scriptable):
                if isinstance(actor, kurt.Stage) or actor.is_visible:
                    self.draw_sprite(actor, self.surface)

        pygame.display.flip()

    def draw_sprite(self, sprite, onto_surface):
        surface = self.surfaces[sprite.costume.image]
        if isinstance(sprite, kurt.Stage):
            rect = ((0, 0), kurt.Stage.SIZE)
        else:
            rect = tuple(self.rect_to_screen(elda.bounds(sprite)))
            angle = -(sprite.direction - 90)
            scale = sprite.size / 100
            surface = pygame.transform.rotozoom(surface, angle, scale)
        onto_surface.blit(surface, rect)

    def pos_to_screen(self, (x, y)):
        return (x + 240,  180 - y)
    
    def rect_to_screen(self, rect):
        return pygame.Rect(self.pos_to_screen(rect.topleft), rect.size)

    def pos_from_screen(self, (x, y)):
        return (x - 240, 180 - y)

    # ScriptEvent handlers

    def clear(self):
        self.pen_surface.fill((0,0,0,0))

    def stamp(self, sprite):
        self.draw_sprite(sprite, self.pen_surface)

    # Script methods

    def get_mouse_pos(self):
        return self.pos_from_screen(pygame.mouse.get_pos())

    def is_mouse_down(self):
        return pygame.mouse.get_pressed()[0]

    def is_key_pressed(self, name):
        if name.endswith(" arrow"):
            name = name[:-6]
        key = self.KEYS_BY_NAME[name]
        return pygame.key.get_pressed()[key]

    def touching_mouse(self, sprite):
        return True # TODO filter collide

    def touching_sprite(self, sprite, other):
        return True # TODO filter collide

    def touching_color(self, sprite, color):
        return False # TODO

    def touching_color_over(self, sprite, color, over):
        return False # TODO

    def ask(self, scriptable, prompt):
        # sync: yield while waiting for answer.
        while 0: # TODO
            yield
        yield ""

    def play_sound(self, sound):
        pass # TODO

    def play_sound_until_done(self, sound):
        self.play_sound(sound)
        while 0: # sync: yield while playing
            yield

    def stop_sounds(self):
        pass # TODO


def main(project):
    sprite = project.sprites[0]

    screen = PygameScreen()
    screen.set_project(project)
    screen.tick()

    interpreter = screen.interpreter
    interpreter.start()

    print "Ctrl+D or `;` to evaluate input"
    print "Extra commands: start, stop"
    print "=>%s" % sprite.name
    while screen.running:
        print "-----"
        text = ""
        while not text.endswith(";"):
            line = None
            while not line:
                screen.tick()
                if not screen.running:
                    return

                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    line = sys.stdin.readline()
                    if not line: # stdin closed
                        line = ";"

            if text:
                text += "\n"
            text += line.strip()

            if text == "start":
                interpreter.start()
                text = ""
            elif text == "stop":
                interpreter.stop()
                text = ""
            elif text == "save":
                path = project.save()
                print "Saved to %r" % path
                text = ""
            elif text.startswith("/"):
                name = text[1:]
                if name:
                    if name == "Stage":
                        sprite = project.stage
                    else:
                        sprite = project.get_sprite(name) or sprite
                    print "=>%s" % sprite.name
                else:
                    for other in [project.stage] + project.sprites:
                        print other.name + (" *" if other == sprite else "")
                text = ""

            if not text:
                break

        text = text.rstrip().rstrip(";")
        if text:
            try:
                script = kurt.text.parse_expression(text.strip(), sprite)
            except SyntaxError, e:
                print "File %r, line %i" % (e.filename, e.lineno)
                print "  %s" % e.text
                print "  " + " " * e.offset + "^"
                print "%s: %s" % (e.__class__.__name__, e.msg)
            else:
                if isinstance(script, kurt.Block) and script.type.shape in (
                        "reporter", "boolean"):
                    print repr(interpreter.evaluate(sprite, script))
                else:
                    if isinstance(script, kurt.Block):
                        script = [script]
                    if isinstance(script, list):
                        script = kurt.Script(script)

                        if script.blocks[0].type.shape == "hat":
                            sprite.scripts.append(script)
                            print "=>Ok."
                        else:
                            print "..."
                            evaluating = [True]
                            def done(thread, evaluating=evaluating):
                                evaluating[0] = False
                            interpreter.push_script(sprite, script,
                                                    callback=done)
                            if not script[-1].type.has_command("doForever"):
                                while evaluating[0] and screen.running:
                                    screen.tick()
                    else:
                        print "=>Not a script!"


if __name__ == "__main__":
    if len(sys.argv) == 2:
        project = kurt.Project.load(sys.argv[1])
    else:
        project = kurt.Project()
        project.sprites = [kurt.Sprite(project, "Sprite1")]
    main(project)


