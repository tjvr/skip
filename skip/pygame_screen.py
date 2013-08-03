"""A Pygame-based view for a Scratch interpreter."""

import select
import signal
import sys

import pygame

import kurt
import skip
from skip import Rect, ScreenEvent


# TODO pen drawing
# TODO text: say, ask, variable/list watchers
# TODO sound



def blit_alpha(dest, source, pos, opacity):
    """Hack: blit per-pixel alpha source onto dest with surface opacity."""
    # http://www.nerdparadise.com/tech/python/pygame/blitopacity/
    (x, y) = pos
    temp = pygame.Surface((source.get_width(), source.get_height())).convert()
    temp.blit(dest, (-x, -y))
    temp.blit(source, (0, 0))
    temp.set_alpha(opacity)
    dest.blit(temp, pos)

def color_mask(surface, color):
    if isinstance(color, kurt.Color):
        color = color.value
    surface = surface.convert()
    surface.set_colorkey(color)
    color_mask = pygame.mask.from_surface(surface)
    color_mask.invert()
    return color_mask



class PygameScreen(skip.Screen):
    CAPTION = "SKIP"
    KEYS_BY_NAME = {}

    def __init__(self):
        self.surface = pygame.display.set_mode(kurt.Stage.SIZE)
        pygame.display.set_caption(self.CAPTION)

        self.pen_surface = pygame.Surface(kurt.Stage.SIZE).convert_alpha()
        self.clear()

        self.clock = pygame.time.Clock()

        self.running = True
        self.surfaces = {}
        self.masks = {}

        for constant in dir(pygame):
            if constant.startswith("K_"):
                key = eval("pygame."+constant)
                name = pygame.key.name(key)
                self.KEYS_BY_NAME[name] = key

    def set_project(self, project):
        skip.Screen.set_project(self, project)
        if project.name:
            pygame.display.set_caption(project.name + " : " + self.CAPTION)
        else:
            pygame.display.set_caption(self.CAPTION)
        for scriptable in [project.stage] + project.sprites:
            for costume in scriptable.costumes:
                p_i = costume.image.pil_image
                assert p_i.mode in ("RGB", "RGBA")
                surface = pygame.image.fromstring(
                        p_i.tostring(), p_i.size, p_i.mode).convert_alpha()
                self.surfaces[costume.image] = surface
                self.masks[costume.image] = pygame.mask.from_surface(surface)

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
                if event.button == 1:
                    yield ScreenEvent("mouse_down")
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    yield ScreenEvent("mouse_up")

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
                if actor.is_visible:
                    self.draw_sprite(actor, self.surface)

        pygame.display.flip()

    def draw_sprite(self, sprite, onto_surface, offset=None):
        surface = self.surfaces[sprite.costume.image]
        if isinstance(sprite, kurt.Stage):
            pos = (0, 0)
        else:
            pos = self.pos_to_screen(skip.bounds(sprite).topleft)
            angle = -(sprite.direction - 90)
            scale = sprite.size / 100
            surface = pygame.transform.rotozoom(surface, angle, scale)

        if offset:
            (ox, oy) = offset
            (x, y) = pos
            pos = (x + ox, y + oy)

        ghost = sprite.graphic_effects['ghost']
        if ghost != 0:
            opacity = (100 - abs(ghost)) * 2.55
            blit_alpha(onto_surface, surface, pos, opacity)
        else:
            onto_surface.blit(surface, pos)

    def pos_to_screen(self, (x, y)):
        return (x + 240,  180 - y)

    def pos_from_screen(self, (x, y)):
        return (x - 240, 180 - y)

    def draw_stage_without_sprite(self, sprite):
        rect = skip.bounds(sprite)
        (x, y) = self.pos_to_screen(rect.topleft)
        offset = (-x, -y)
        surface = pygame.Surface(rect.size).convert_alpha()
        self.draw_sprite(self.project.stage, surface, offset)
        surface.blit(self.pen_surface, (0, 0))
        for actor in self.project.actors:
            if actor is not sprite:
                if isinstance(actor, kurt.Scriptable):
                    if actor.is_visible:
                        self.draw_sprite(actor, surface, offset)
        return surface

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
        mask = self.masks[sprite.costume.image]
        (x, y) = self.pos_to_screen(skip.bounds(sprite).topleft)
        (mx, my) = pygame.mouse.get_pos()
        return bool(mask.get_at((int(mx - x), int(my - y))))

    def touching_sprite(self, sprite, other):
        mask = self.masks[sprite.costume.image]
        other_mask = self.masks[other.costume.image]
        (ox, oy) = self.pos_to_screen(skip.bounds(other).topleft)
        offset = (int(ox - x), int(oy - y))
        return bool(mask.overlap(other_mask, offset))

    def touching_color(self, sprite, color):
        stage_surface = self.draw_stage_without_sprite(sprite)
        stage_mask = color_mask(stage_surface, color)
        sprite_mask = self.masks[sprite.costume.image]
        return bool(stage_mask.overlap(sprite_mask, (0, 0)))

    def touching_color_over(self, sprite, color, over):
        stage_surface = self.draw_stage_without_sprite(sprite)
        stage_mask = color_mask(stage_surface, over)
        sprite_surface = self.surfaces[sprite.costume.image]
        sprite_mask = color_mask(sprite_surface, color)
        return bool(stage_mask.overlap(sprite_mask, (0, 0)))

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



if __name__ == "__main__":
    project = None
    if len(sys.argv) == 2:
        project = kurt.Project.load(sys.argv[1])

    def signal_handler(signal, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)

    skip.main(project, PygameScreen())

