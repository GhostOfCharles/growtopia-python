"""Responsive gameplay HUD layout and drawing helpers."""

from dataclasses import dataclass

import pygame


NAVY = (18, 35, 62)
PANEL = (26, 49, 82)
PANEL_LIGHT = (39, 68, 108)
TEXT = (235, 242, 252)
MUTED = (166, 187, 215)
GOLD = (255, 195, 67)
GREEN = (74, 201, 92)
RED = (157, 57, 65)


@dataclass
class HUDLayout:
    width: int
    height: int
    scale: float = 1.0

    def __post_init__(self):
        self.width, self.height = max(1, int(self.width)), max(1, int(self.height))
        self.scale = max(.75, min(1.25, float(self.scale)))
        self.margin = max(8, round(min(self.width, self.height) * .016))
        self.slot_size = max(42, min(round(64 * self.scale), (self.width - 40) // 8 - 5))
        self.slot_gap = max(4, round(7 * self.scale))
        self.slot_size = min(self.slot_size,
                             max(36, (self.width - 2 * self.margin - 7 * self.slot_gap) // 8))
        total_w = 8 * self.slot_size + 7 * self.slot_gap
        slot_y = self.height - self.slot_size - max(12, round(18 * self.scale))
        self.hotbar_slots = tuple(
            pygame.Rect((self.width - total_w) // 2 + i * (self.slot_size + self.slot_gap),
                        slot_y, self.slot_size, self.slot_size)
            for i in range(8))
        self.hotbar_panel = self.hotbar_slots[0].union(self.hotbar_slots[-1]).inflate(
            round(16 * self.scale), round(14 * self.scale))
        self.item_label = pygame.Rect(self.width // 2 - round(100 * self.scale),
                                      self.hotbar_panel.top - round(31 * self.scale),
                                      round(200 * self.scale), round(25 * self.scale))

        right_size = round(46 * self.scale)
        self.pause_button = pygame.Rect(self.width - self.margin - right_size,
                                        self.margin, right_size, right_size)
        world_w = min(round(204 * self.scale), max(120, self.width // 3))
        world_h = round(50 * self.scale)
        self.world_panel = pygame.Rect((self.width - world_w) // 2, self.margin,
                                       world_w, world_h)
        left_w = min(round(290 * self.scale), max(150, self.width // 2))
        if self.world_panel.left < left_w + self.margin * 2:
            left_w = max(150, self.world_panel.left - self.margin * 2)
        self.player_panel = pygame.Rect(self.margin, self.margin, left_w,
                                        round(70 * self.scale))
        self.hp_bar = pygame.Rect(self.player_panel.x + round(48 * self.scale),
                                  self.player_panel.bottom - round(23 * self.scale),
                                  max(24, self.player_panel.width - round(166 * self.scale)),
                                  round(10 * self.scale))
        self.hp_value_x = self.player_panel.right - round(12 * self.scale)

        panel_w = min(round(390 * self.scale), self.width - 2 * self.margin)
        panel_h = min(round(350 * self.scale), self.height - 2 * self.margin)
        self.pause_panel = pygame.Rect((self.width - panel_w) // 2,
                                       (self.height - panel_h) // 2,
                                       panel_w, panel_h)
        self.pause_buttons = self._pause_buttons()

    def _pause_buttons(self):
        margin = max(12, round(22 * self.scale))
        gap = max(7, round(10 * self.scale))
        top = self.pause_panel.y + round(72 * self.scale)
        available_h = self.pause_panel.bottom - top - margin
        labels = ("Resume Game", "Settings", "Controls", "Save and Exit")
        button_h = min(round(54 * self.scale),
                       max(38, (available_h - gap * (len(labels) - 1)) // len(labels)))
        return tuple((pygame.Rect(self.pause_panel.x + margin,
                                  top + i * (button_h + gap),
                                  self.pause_panel.width - margin * 2, button_h), label)
                     for i, label in enumerate(labels))

    @property
    def protected_rects(self):
        return self.player_panel, self.world_panel, self.pause_button, self.hotbar_panel, self.item_label


class HUDRenderer:
    def __init__(self, size, scale=1.0):
        self.scale = scale
        self.resize(size)

    def resize(self, size):
        size = tuple(map(int, size))
        if not hasattr(self, "layout") or (self.layout.width, self.layout.height) != size:
            self.layout = HUDLayout(*size, scale=self.scale)
        return self.layout

    def set_scale(self, scale):
        self.scale = max(.75, min(1.25, float(scale)))
        self.layout = HUDLayout(self.layout.width, self.layout.height, self.scale)
        return self.layout

    @staticmethod
    def _panel(surface, rect, fill=PANEL, border=(8, 19, 36), radius=9, width=2):
        pygame.draw.rect(surface, fill, rect, border_radius=radius)
        pygame.draw.rect(surface, border, rect, width=width, border_radius=radius)

    def draw_top(self, surface, username, world_name, hp, max_hp, font, label_font):
        layout = self.layout
        self._panel(surface, layout.player_panel)
        name = font.render("@" + username, True, TEXT)
        name_rect = name.get_rect(midleft=(layout.player_panel.x + 12, layout.player_panel.y + 19))
        surface.blit(name, name_rect)
        pygame.draw.rect(surface, NAVY, layout.hp_bar, border_radius=5)
        ratio = max(0.0, min(1.0, hp / max(1.0, max_hp)))
        if ratio:
            fill = layout.hp_bar.copy()
            fill.width = max(1, round(fill.width * ratio))
            pygame.draw.rect(surface, GREEN, fill, border_radius=5)
        pygame.draw.rect(surface, (6, 16, 28), layout.hp_bar, width=1, border_radius=5)
        hp_label = label_font.render("HP", True, MUTED)
        hp_rect = hp_label.get_rect(midleft=(layout.player_panel.x + round(12 * layout.scale),
                                             layout.hp_bar.centery))
        surface.blit(hp_label, hp_rect)
        hp_value = label_font.render(f"{int(hp)}/{int(max_hp)}", True, TEXT)
        surface.blit(hp_value, hp_value.get_rect(midright=(layout.hp_value_x,
                                                           layout.hp_bar.centery)))

        self._panel(surface, layout.world_panel)
        title = label_font.render(world_name, True, TEXT)
        max_width = layout.world_panel.width - 20
        shortened = world_name
        while title.get_width() > max_width and len(shortened) > 1:
            shortened = shortened[:-2] + "…"
            title = label_font.render(shortened, True, TEXT)
        surface.blit(title, title.get_rect(center=layout.world_panel.center))

        self._panel(surface, layout.pause_button, fill=PANEL_LIGHT, radius=8)
        x, y = layout.pause_button.center
        bar_h = max(12, round(17 * layout.scale))
        bar_w = max(3, round(4 * layout.scale))
        pygame.draw.rect(surface, TEXT, (x - bar_w - 3, y - bar_h // 2, bar_w, bar_h), border_radius=2)
        pygame.draw.rect(surface, TEXT, (x + 3, y - bar_h // 2, bar_w, bar_h), border_radius=2)

    def draw_context(self, surface, text, font):
        rect = self.layout.item_label
        self._panel(surface, rect, fill=NAVY, radius=7, width=1)
        label = font.render(text, True, TEXT)
        surface.blit(label, label.get_rect(center=rect.center))

    def draw_debug(self, surface, lines, font):
        if not lines:
            return
        padding, line_h = 10, font.get_linesize()
        rendered = [font.render(line, True, TEXT) for line in lines]
        width = max(text.get_width() for text in rendered) + padding * 2
        height = len(rendered) * line_h + padding * 2
        rect = pygame.Rect(self.layout.width - width - self.layout.margin,
                           self.layout.pause_button.bottom + 8, width, height)
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((*NAVY, 220))
        surface.blit(overlay, rect.topleft)
        pygame.draw.rect(surface, GOLD, rect, width=1, border_radius=6)
        for i, text in enumerate(rendered):
            surface.blit(text, (rect.x + padding, rect.y + padding + i * line_h))

    def pause_button_rects(self, page="main"):
        if page == "main":
            return self.layout.pause_buttons
        margin = max(12, round(22 * self.scale))
        rect = pygame.Rect(self.layout.pause_panel.x + margin,
                           self.layout.pause_panel.bottom - round(62 * self.scale),
                           self.layout.pause_panel.width - margin * 2,
                           round(48 * self.scale))
        return ((rect, "Back"),)

    def draw_pause(self, surface, page, font, title_font, body_font, hud_scale=1.0):
        shade = pygame.Surface((self.layout.width, self.layout.height), pygame.SRCALPHA)
        shade.fill((5, 12, 25, 155))
        surface.blit(shade, (0, 0))
        panel = self.layout.pause_panel
        self._panel(surface, panel, fill=NAVY, border=(74, 104, 148), radius=14, width=2)
        title_text = {"main": "Paused", "settings": "Settings", "controls": "Controls"}.get(page, "Paused")
        title = title_font.render(title_text, True, TEXT)
        surface.blit(title, title.get_rect(center=(panel.centerx, panel.y + round(38 * self.scale))))

        if page == "settings":
            text = body_font.render(f"HUD size: {round(hud_scale * 100)}%", True, MUTED)
            surface.blit(text, text.get_rect(center=(panel.centerx, panel.centery - 20)))
            # Scale controls are drawn as a compact pair above Back.
            controls = self._settings_controls()
            for rect, label in controls:
                self._draw_button(surface, rect, label, font)
        elif page == "controls":
            lines = ("Move: A / D or Arrow keys", "Jump: W, Up, or Space",
                     "Punch / place: mouse click or hold", "Select slot: 1-8 or mouse wheel",
                     "Dash: Q", "Pause: Escape")
            line_h = body_font.get_linesize()
            start_y = panel.y + round(88 * self.scale)
            for i, line in enumerate(lines):
                text = body_font.render(line, True, MUTED)
                surface.blit(text, text.get_rect(center=(panel.centerx, start_y + i * line_h)))

        for rect, label in self.pause_button_rects(page):
            self._draw_button(surface, rect, label, font,
                              danger=(label == "Save and Exit"))

    def _settings_controls(self):
        panel = self.layout.pause_panel
        w = max(42, round(52 * self.scale))
        h = max(38, round(42 * self.scale))
        gap = 10
        center_y = panel.centery + 24
        return ((pygame.Rect(panel.centerx - w - gap // 2, center_y, w, h), "−"),
                (pygame.Rect(panel.centerx + gap // 2, center_y, w, h), "+"))

    def _draw_button(self, surface, rect, label, font, danger=False):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        fill = RED if danger else (PANEL_LIGHT if hovered else PANEL)
        self._panel(surface, rect, fill=fill, border=GOLD if hovered else (8, 19, 36),
                    radius=8, width=2)
        text = font.render(label, True, TEXT)
        surface.blit(text, text.get_rect(center=rect.center))

    def pause_action_at(self, position, page="main"):
        if page == "settings":
            for rect, label in self._settings_controls():
                if rect.collidepoint(position):
                    return "scale_down" if label == "−" else "scale_up"
        for rect, label in self.pause_button_rects(page):
            if rect.collidepoint(position):
                return {"Resume Game": "resume", "Settings": "settings",
                        "Controls": "controls", "Save and Exit": "save_exit",
                        "Back": "back"}.get(label)
        return None
