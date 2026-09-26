"""App-wide theme, applied once at startup from AppConfig.theme.

Three named, purpose-built themes ("Editorial Light" / broadsheet, "Walnut
Library" / woodshelf, "Midnight Ink" / inkynight -- originally "Tờ Báo
Sáng" / "Kệ Sách Gỗ" / "Mực Đêm"; the keys stay as they were so saved
configs keep working) share one design language (paper-toned
content area, a single cyan accent, hairline borders, gradient cover
placeholders) but differ in how light/dark their *chrome* (sidebar, top
chrome, detail panel, status bar) is -- Inky Night in particular keeps its
grid/list *content* area light even though every other surface is dark, so
"the theme" can't be a single light-vs-dark palette the way the old
LIGHT/DARK pair was.

Token semantics (read this before adding a new widget's stylesheet):
- `background` / `surface`: the app's *chrome* family -- top bar, menus,
  dialogs, tooltips, input fields. Dark for Inky Night, light for the other
  two. Always pair these with `sidebar_text`, never `text` -- `text` is
  fixed dark because the content area is always light, so pairing it with a
  potentially-dark `background`/`surface` would (and on Inky Night, did,
  before this token split existed) render invisible dark-on-dark text.
- `content_bg`: the library grid/list's own background. Equal to
  `background` for Broadsheet/Woodshelf; the one place Inky Night stays
  light. Always pairs with `text` (always dark).
- `sidebar_bg` / `sidebar_text`: the sidebar's own background/text -- also
  reused for any other chrome surface that sits directly on `background`
  (e.g. the menu bar), since both are "text on the chrome-family color."
- `panel_bg` / `panel_text`: the Document Detail Panel's own background/
  text -- an explicit matched pair, independent of `background`/`surface`,
  since Inky Night wants a dark panel while its content area is light.
- `muted_text`: secondary/hint text, only ever used against `sidebar_bg`/
  `panel_bg` today (never against `content_bg`) -- one value per theme is
  enough because both of those are always the same light/dark family
  within a given theme.
- `selected_bg` / `selected_border` / `selected_text`: the shared
  "selected item" look (cyan-tinted background, cyan left border, cyan-ish
  text) -- deliberately identical across all 3 themes per the design spec.
- `cover_gradients` / `cover_spine`: see presentation/cover_placeholder.py.

Adding a theme (no other code changes needed):
1. Define one more `ThemeColors(...)` below -- every token, plus the
   structural options (layout_mode, sidebar_style, header/slider/chips
   flags, labels) that describe how its chrome is arranged.
2. Add it to THEMES and its key to core.config.THEME_CHOICES (the order
   there is the order shown in the theme pickers).
3. Run the tests: tests/test_theme_contract.py validates every theme with
   validate_theme() (parseable colors, known layout options, WCAG contrast
   for every text/background pair) and builds the real main window in it.
Widgets must never branch on a theme's `key` -- only on these declared
options -- so a new theme can't silently fall into another theme's code
path.

Widgets with custom stylesheets (sidebar, omnibar, main window chrome, the
detail panel, ...) pull their colors from `current_colors()` rather than
hardcoding hex values, so they follow whichever theme was applied at
startup instead of silently staying on one look forever. Changing the theme
in Settings takes effect on next launch, not live -- live-updating every
already-built stylesheet in place was judged not worth the complexity here.
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# Not a real installed font on a fresh Windows machine (or anywhere else,
# without shipping the actual files) -- this fallback list at least gets
# Qt to substitute the closest available serif instead of silently
# dropping to the platform's default sans-serif UI font. Dropping real
# Source Serif 4 .ttf/.otf files into a new presentation/assets/fonts/ dir
# (loaded via QFontDatabase.addApplicationFont) later would get pixel-exact
# fidelity; this is a pragmatic placeholder until then.
SERIF_FONT_FAMILIES = ["Source Serif 4", "Noto Serif", "Georgia", "Cambria", "Times New Roman"]
MONO_FONT_FAMILIES = ("IBM Plex Mono", "Cascadia Mono", "Consolas", "Courier New")
SANS_LIGHT_FONT_FAMILIES = ("Segoe UI", "Helvetica Neue", "Arial")
# Every theme has its own typeface, so switching theme visibly switches the
# font too. Each list is tried in order (the first one installed wins) and
# ends in fonts that ship with Windows and cover Vietnamese.
CLASSIC_SERIF_FONT_FAMILIES = ("Palatino Linotype", "Book Antiqua", "Georgia", "Times New Roman")  # warm old-style serif
LITERARY_FONT_FAMILIES = ("Sitka Text", "Cambria", "Georgia", "Times New Roman")  # a book-text serif for the dark ink look
ROUNDED_FONT_FAMILIES = ("Nunito", "Candara", "Trebuchet MS", "Segoe UI")  # soft, friendly humanist sans
CALM_SANS_FONT_FAMILIES = ("Noto Sans", "Calibri", "Segoe UI", "Arial")  # quiet, even sans


@dataclass(frozen=True)
class ThemeColors:
    key: str
    display_name: str
    background: str
    content_bg: str
    surface: str
    sidebar_bg: str
    sidebar_text: str
    panel_bg: str
    panel_text: str
    # The full-width top bar (brand, search, view/sort controls).
    header_bg: str
    text: str
    muted_text: str
    border: str
    accent: str
    accent_text: str
    selected_bg: str
    selected_border: str
    selected_text: str
    cover_gradients: tuple[tuple[str, str], ...]
    cover_spine: tuple[int, int, int, int]
    # Structural, not just cosmetic -- each theme is designed around a
    # specific grid density (see layout_mode below), so the cover width
    # that density assumes ships with the theme rather than being one
    # global default. The toolbar's size slider still overrides it freely
    # for the rest of the session.
    default_cover_width: int
    # "detail_panel": sidebar | library | right-hand detail panel.
    # "action_bar":   sidebar | library, with a selection action bar
    #                 pinned to the bottom instead of a detail panel.
    layout_mode: str
    # True for themes whose sidebar collapses to an icon-only rail.
    icon_rail_sidebar: bool
    # -- Structural options with defaults (see "Adding a theme" above) --
    # "plain": name + muted count rows. "iconic": taller rows with line
    # icons and a count pill on the selected row.
    sidebar_style: str = "plain"
    # The "everything" row's label.
    all_items_label: str = "Tất cả tài liệu"
    # Header extras: the cover-size slider.
    show_cover_size_slider: bool = True

    # -- Style options ("mood" themes). Every default reproduces the look
    # the three original themes already had, so they need no changes. --
    # Typography: app + content font fallback list, weight (CSS scale,
    # 300 = light), letter spacing in percent (100 = normal), card title
    # weight, and the smallest pixel size for text printed on covers.
    font_families: tuple[str, ...] = tuple(SERIF_FONT_FAMILIES)
    font_weight: int = 400
    letter_spacing: float = 100.0
    card_title_weight: int = 600
    jacket_min_px: int = 6
    # "normal" or "code" (lower_snake_case labels, "// " section headings).
    label_style: str = "normal"
    # Corner radii (px): covers/cards, search box & buttons.
    cover_radius: int = 2
    control_radius: int = 3
    # Covers: optional 1px border; flat (first gradient color only) instead
    # of a gradient; whether a
    # coverless book gets its title printed on the placeholder, and in
    # which color.
    cover_border_color: str | None = None
    cover_flat: bool = False
    cover_jacket_text: bool = True
    cover_text_color: str = "#ffffff"
    # Selected sidebar row: "stripe" (band + left stripe), "fill" (rounded
    # band), "outline" (1px accent box) or "underline" (accent line under
    # the name, no band).
    selection_style: str = "stripe"
    # Clickable actions (detail panel, header add button, dialog buttons):
    # "default", "link" (underlined text), "bracket" ("[ action ]") or
    # "soft" (faint filled box).
    action_style: str = "default"
    # Search box: "box", "pill" or "underline".
    search_style: str = "box"
    # Retro OS title bar strip at the top of the window (None = none).
    titlebar_text: str | None = None
    # Film-grain overlay over the whole window.
    grain_overlay: bool = False
    # Hover/selection fade duration in ms (0 = instant).
    motion_ms: int = 0
    # Library grid: "uniform", or "featured" (the page's first book shown
    # large beside the grid).
    grid_layout: str = "uniform"


# Shared across all 3 themes -- muted, book-spine-like tones for the cover
# placeholder gradient (see cover_placeholder.py), picked deterministically
# per document so the same book always gets the same look, but different
# books in the same library look visually varied instead of one flat block.
_COVER_GRADIENTS: tuple[tuple[str, str], ...] = (
    ("#6e1f24", "#3a1113"),  # oxblood
    ("#5c3a22", "#2e1b10"),  # leather brown
    ("#1f4f5a", "#0f2c34"),  # deep teal
    ("#1d3160", "#0e1a36"),  # navy
    ("#172441", "#0a1022"),  # midnight
    ("#1d3d28", "#0e2215"),  # forest green
    ("#3a2b63", "#1d1636"),  # plum
    ("#1f5a45", "#103326"),  # bottle green
)
# A thin, slightly darker band down the left edge -- a hint of a book
# spine, not a solid block. (A plain RGBA tuple rather than a CSS rgba()
# string: QColor can't parse the latter, which is what used to paint this
# band solid black.)
_COVER_SPINE = (0, 0, 0, 55)

# Shared across all 3 themes -- the spec calls these out as one universal
# "selected item" treatment, not per-theme.
_SELECTED_BG = "#e9f8ff"
_SELECTED_BORDER = "#0088b0"
_SELECTED_TEXT = "#006786"
_ACCENT = "#0088b0"
_ACCENT_TEXT = "#ffffff"

BROADSHEET = ThemeColors(
    key="broadsheet",
    display_name="Editorial Light",
    background="#f3f2f1",
    content_bg="#f3f2f1",
    surface="#ffffff",
    sidebar_bg="#ecebea",
    sidebar_text="#201e1d",
    panel_bg="#efeeed",
    panel_text="#201e1d",
    header_bg="#f8f7f6",
    text="#201e1d",
    muted_text="#8a8680",
    border="rgba(32,30,29,.12)",
    accent=_ACCENT,
    accent_text=_ACCENT_TEXT,
    selected_bg=_SELECTED_BG,
    selected_border=_SELECTED_BORDER,
    selected_text=_SELECTED_TEXT,
    cover_gradients=_COVER_GRADIENTS,
    cover_spine=_COVER_SPINE,
    default_cover_width=104,  # 104x138 covers, generous gutters (see library_view's card delegate)
    layout_mode="detail_panel",
    icon_rail_sidebar=False,
)

WOODSHELF = ThemeColors(
    key="woodshelf",
    display_name="Walnut Library",
    background="#f0ebe1",
    content_bg="#f0ebe1",
    surface="#ffffff",
    sidebar_bg="#ffffff",
    sidebar_text="#201e1d",
    panel_bg="#ffffff",
    panel_text="#201e1d",
    header_bg="#f8f5ef",
    text="#201e1d",
    muted_text="#6b6863",
    border="rgba(32,30,29,.12)",
    accent=_ACCENT,
    accent_text=_ACCENT_TEXT,
    selected_bg=_SELECTED_BG,
    selected_border=_SELECTED_BORDER,
    selected_text=_SELECTED_TEXT,
    cover_gradients=_COVER_GRADIENTS,
    cover_spine=_COVER_SPINE,
    default_cover_width=160,  # big 160x227 covers -- the shelf is the point of this theme
    layout_mode="action_bar",
    icon_rail_sidebar=False,
    sidebar_style="iconic",
    all_items_label="Tất cả",
    show_cover_size_slider=False,  # this theme's big covers are its point
    font_families=CLASSIC_SERIF_FONT_FAMILIES,
)

INKYNIGHT = ThemeColors(
    key="inkynight",
    display_name="Midnight Ink",
    background="#201e1d",
    content_bg="#f3f2f2",  # the one theme where content stays light while chrome goes dark
    surface="#2d2b2b",
    sidebar_bg="#201e1d",
    sidebar_text="#e5e2de",
    panel_bg="#282626",
    panel_text="#e5e2de",
    header_bg="#201e1d",
    text="#201e1d",
    muted_text="#9a958d",
    # A dark-at-12%-opacity hairline (the literal spec value) would be
    # invisible against this theme's dark chrome -- inverted to a light
    # hairline instead so borders actually separate anything here.
    border="rgba(255,255,255,.15)",
    accent=_ACCENT,
    accent_text=_ACCENT_TEXT,
    selected_bg=_SELECTED_BG,
    selected_border=_SELECTED_BORDER,
    selected_text=_SELECTED_TEXT,
    cover_gradients=_COVER_GRADIENTS,
    cover_spine=_COVER_SPINE,
    default_cover_width=120,
    layout_mode="detail_panel",
    icon_rail_sidebar=True,
    font_families=LITERARY_FONT_FAMILIES,
)

# -- Mood themes ------------------------------------------------------------

HEALING = ThemeColors(  # "Không Gian Chữa Lành" -- Cottagecore & Ghibli
    key="healing",
    display_name="Không Gian Chữa Lành",
    background="#f5efe0",
    content_bg="#f5efe0",
    surface="#fbf7ec",
    sidebar_bg="#efe6d2",
    sidebar_text="#4a4030",
    panel_bg="#efe6d2",
    panel_text="#4a4030",
    header_bg="#f5efe0",
    text="#4a4030",
    muted_text="#7d6a52",
    border="rgba(107,85,64,.16)",
    accent="#6f8766",
    accent_text="#ffffff",
    selected_bg="#e9e2cd",
    selected_border="#7c9473",
    selected_text="#4a4030",
    cover_gradients=(
        ("#87967b", "#667a5c"),  # sage
        ("#a67c5b", "#80603f"),  # clay
        ("#c17a55", "#9c5a3a"),  # terracotta
        ("#ac877b", "#94705f"),  # dusty rose
        ("#7c9473", "#5a7152"),  # moss
        ("#ac8b3f", "#8f7229"),  # honey
        ("#968aa3", "#766a84"),  # heather
        ("#9d8e73", "#817259"),  # wheat
    ),
    cover_spine=(74, 64, 48, 40),
    default_cover_width=136,
    layout_mode="detail_panel",
    icon_rail_sidebar=False,
    all_items_label="Tất cả",
    show_cover_size_slider=False,
    cover_radius=12,
    control_radius=18,
    selection_style="fill",
    search_style="pill",
    grain_overlay=True,
    card_title_weight=700,
    font_families=ROUNDED_FONT_FAMILIES,
)

RETRO_TECH = ThemeColors(  # "Hoài Niệm Kỹ Thuật Số" -- Lo-Fi Retro-Tech
    key="retro_tech",
    display_name="Hoài Niệm Kỹ Thuật Số",
    background="#1f2233",
    content_bg="#1f2233",
    surface="#171927",
    sidebar_bg="#1f2233",
    sidebar_text="#c9cde6",
    panel_bg="#1f2233",
    panel_text="#d7dbf0",
    header_bg="#1f2233",
    text="#d7dbf0",
    muted_text="#8a8fb0",
    border="#3a3e56",
    accent="#9fe3ee",
    accent_text="#1f2233",
    selected_bg="#262a40",
    selected_border="#9fe3ee",
    selected_text="#9fe3ee",
    cover_gradients=tuple((c, c) for c in (
        "#f2a69a", "#a6c8f2", "#9fe3ee", "#f2a6d0", "#a6e0b0", "#f2d9a0", "#c8a6f2", "#b8c4dc",
    )),
    cover_spine=(0, 0, 0, 0),
    default_cover_width=120,
    layout_mode="detail_panel",
    icon_rail_sidebar=False,
    show_cover_size_slider=False,
    font_families=MONO_FONT_FAMILIES,
    jacket_min_px=9,
    label_style="code",
    all_items_label="Tất cả",
    cover_radius=0,
    control_radius=0,
    cover_border_color="#3a3e56",
    cover_flat=True,
    cover_text_color="#1f2233",
    selection_style="outline",
    action_style="bracket",
    titlebar_text="~/smartdoc — thư viện.app",
)

JAPANDI = ThemeColors(  # "Japandi Tối Giản"
    key="japandi",
    display_name="Japandi Tối Giản",
    background="#f1ece1",
    content_bg="#f1ece1",
    surface="#f6f2ea",
    sidebar_bg="#f1ece1",
    sidebar_text="#3d3730",
    panel_bg="#f1ece1",
    panel_text="#3d3730",
    header_bg="#f1ece1",
    text="#3d3730",
    muted_text="#7d7466",
    border="rgba(61,55,48,.14)",
    accent="#a86b4f",
    accent_text="#ffffff",
    selected_bg="#e9e2d4",
    selected_border="#b3775a",
    selected_text="#3d3730",
    cover_gradients=tuple((c, c) for c in (
        "#7d7464", "#b3775a", "#a5a295", "#9d8458", "#c4b392", "#8c8a7a", "#6f6a5e", "#b9a68a",
    )),
    cover_spine=(0, 0, 0, 0),
    default_cover_width=150,
    layout_mode="detail_panel",
    icon_rail_sidebar=False,
    show_cover_size_slider=False,
    font_families=SANS_LIGHT_FONT_FAMILIES,
    font_weight=300,
    letter_spacing=102.0,
    card_title_weight=400,
    cover_radius=2,
    control_radius=0,
    cover_flat=True,
    cover_jacket_text=False,
    selection_style="underline",
    action_style="link",
    search_style="underline",
    grid_layout="featured",
)

ZEN_DARK = ThemeColors(  # "Zen Dark Mode"
    key="zen_dark",
    display_name="Zen Dark Mode",
    background="#182a2b",
    content_bg="#182a2b",
    surface="#1d3233",
    sidebar_bg="#182a2b",
    sidebar_text="#d8e4e2",
    panel_bg="#1b2e2f",
    panel_text="#d8e4e2",
    header_bg="#182a2b",
    text="#d8e4e2",
    muted_text="#8aa09d",
    border="rgba(216,228,226,.08)",
    accent="#5fd6c4",
    accent_text="#182a2b",
    selected_bg="#1f3a3a",
    selected_border="#5fd6c4",
    selected_text="#5fd6c4",
    cover_gradients=(
        ("#4a2233", "#2a1420"),  # deep wine
        ("#262a5e", "#161a3a"),  # indigo
        ("#1d4a48", "#12302f"),  # deep teal
        ("#4a1f22", "#2a1214"),  # maroon
        ("#1f3d2a", "#122417"),  # forest
        ("#4a3218", "#2a1c0e"),  # amber
        ("#3a1f4a", "#22122c"),  # plum
        ("#262838", "#16171f"),  # slate
    ),
    cover_spine=(0, 0, 0, 45),
    default_cover_width=120,
    layout_mode="detail_panel",
    icon_rail_sidebar=False,
    show_cover_size_slider=False,
    cover_radius=6,
    control_radius=18,
    selection_style="fill",
    action_style="soft",
    search_style="pill",
    motion_ms=500,
    font_families=CALM_SANS_FONT_FAMILIES,
)

def _with_tokens(colors: ThemeColors, t: dict) -> ThemeColors:
    """`colors` with its colours taken from a theme package's tokens (themes/<id>/theme.json), so widgets that still
    read ThemeColors and widgets styled by ThemeManager show one palette. Structure and type options stay."""
    return dataclasses.replace(
        colors, background=t["bg"], content_bg=t["bg"], surface=t["surface"], sidebar_bg=t["rail"],
        sidebar_text=t["ink"], panel_bg=t["panel"], panel_text=t["ink"], header_bg=t["bg"], text=t["ink"],
        muted_text=t["ink2"], border=t["line"], accent=t["accent"], accent_text=t["accentink"],
        selected_bg=t["accentsoft"], selected_border=t["accent"], selected_text=t["ink"],
    )


def _in_design_tokens(colors: ThemeColors) -> ThemeColors:
    from smartdoc.presentation.theme_manager import TOKEN_KEY_FOR_THEME, load_tokens

    return _with_tokens(colors, load_tokens()[TOKEN_KEY_FOR_THEME[colors.key]])


BROADSHEET, WOODSHELF, INKYNIGHT, HEALING, RETRO_TECH, JAPANDI, ZEN_DARK = (
    _in_design_tokens(c) for c in (BROADSHEET, WOODSHELF, INKYNIGHT, HEALING, RETRO_TECH, JAPANDI, ZEN_DARK))

THEMES: dict[str, ThemeColors] = {
    "broadsheet": BROADSHEET,
    "woodshelf": WOODSHELF,
    "inkynight": INKYNIGHT,
    "healing": HEALING,
    "retro_tech": RETRO_TECH,
    "japandi": JAPANDI,
    "zen_dark": ZEN_DARK,
}

DEFAULT_THEME_KEY = "broadsheet"

LAYOUT_MODES = ("detail_panel", "action_bar")
SIDEBAR_STYLES = ("plain", "iconic")
# Allowed values of the enumerated style options.
STYLE_CHOICES = {
    "label_style": ("normal", "code"),
    "selection_style": ("stripe", "fill", "outline", "underline"),
    "action_style": ("default", "link", "bracket", "soft"),
    "search_style": ("box", "pill", "underline"),
    "grid_layout": ("uniform", "featured"),
}
COLOR_TOKENS = (
    "background", "content_bg", "surface", "sidebar_bg", "sidebar_text", "panel_bg", "panel_text",
    "header_bg", "text", "muted_text", "border", "accent", "accent_text", "selected_bg",
    "selected_border", "selected_text", "cover_text_color",
)

# Minimum WCAG 2.x contrast ratios validate_theme() enforces.
MIN_TEXT_CONTRAST = 4.5  # body text (AA)
MIN_UI_CONTRAST = 3.0  # bold button labels, secondary/muted text (AA large text / UI components)

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_RGBA_COLOR = re.compile(r"^rgba\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*(0|1|0?\.\d+)\s*\)$")
# Tokens used only inside Qt stylesheets may be CSS rgba(); every other
# color token is also fed to QColor/QPalette, which only parses hex.
_STYLESHEET_ONLY_TOKENS = {"border"}


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted((_relative_luminance(foreground), _relative_luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


# (label, foreground token, background token, minimum ratio)
CONTRAST_PAIRS = (
    ("library text", "text", "content_bg", MIN_TEXT_CONTRAST),
    ("sidebar text", "sidebar_text", "sidebar_bg", MIN_TEXT_CONTRAST),
    ("header text", "sidebar_text", "header_bg", MIN_TEXT_CONTRAST),
    ("dialog/menu text", "sidebar_text", "surface", MIN_TEXT_CONTRAST),
    ("window text", "sidebar_text", "background", MIN_TEXT_CONTRAST),
    ("detail panel text", "panel_text", "panel_bg", MIN_TEXT_CONTRAST),
    ("selected item text", "selected_text", "selected_bg", MIN_TEXT_CONTRAST),
    ("accent button label", "accent_text", "accent", MIN_UI_CONTRAST),
    ("muted text on sidebar", "muted_text", "sidebar_bg", MIN_UI_CONTRAST),
    ("muted text on panel", "muted_text", "panel_bg", MIN_UI_CONTRAST),
)


def validate_theme(colors: ThemeColors) -> list[str]:
    """Every problem that would make `colors` render wrongly or illegibly
    -- empty means the theme is safe to ship."""
    problems: list[str] = []
    for name in COLOR_TOKENS:
        value = getattr(colors, name)
        if isinstance(value, str) and _HEX_COLOR.match(value):
            continue
        if name in _STYLESHEET_ONLY_TOKENS and isinstance(value, str) and _RGBA_COLOR.match(value):
            continue
        problems.append(f"{name}: {value!r} is not a #rrggbb color")
    if colors.cover_border_color is not None and not _HEX_COLOR.match(colors.cover_border_color):
        problems.append(f"cover_border_color: {colors.cover_border_color!r} is not a #rrggbb color")
    for option, allowed in STYLE_CHOICES.items():
        if getattr(colors, option) not in allowed:
            problems.append(f"{option} {getattr(colors, option)!r} not in {allowed}")
    if not colors.font_families:
        problems.append("font_families is empty")
    if not 100 <= colors.font_weight <= 900 or not 100 <= colors.card_title_weight <= 900:
        problems.append("font weights must be 100..900")
    if not 0 <= colors.motion_ms <= 1500:
        problems.append(f"motion_ms {colors.motion_ms} outside 0..1500")
    if not colors.key or not re.match(r"^[a-z0-9_]+$", colors.key):
        problems.append(f"key {colors.key!r} must be lower-case letters/digits/underscores")
    if not colors.display_name:
        problems.append("display_name is empty")
    if colors.layout_mode not in LAYOUT_MODES:
        problems.append(f"layout_mode {colors.layout_mode!r} not in {LAYOUT_MODES}")
    if colors.sidebar_style not in SIDEBAR_STYLES:
        problems.append(f"sidebar_style {colors.sidebar_style!r} not in {SIDEBAR_STYLES}")
    if not 60 <= colors.default_cover_width <= 240:
        problems.append(f"default_cover_width {colors.default_cover_width} outside 60..240")
    if not colors.cover_gradients or any(
        not (_HEX_COLOR.match(a) and _HEX_COLOR.match(b)) for a, b in colors.cover_gradients
    ):
        problems.append("cover_gradients must be a non-empty tuple of (#rrggbb, #rrggbb) pairs")
    if len(colors.cover_spine) != 4 or not all(0 <= c <= 255 for c in colors.cover_spine):
        problems.append("cover_spine must be an (r, g, b, a) tuple of 0..255")
    if not problems and colors.cover_jacket_text:
        # Text printed on placeholder covers must be readable on every one.
        for pair in colors.cover_gradients:
            for shade in pair:
                if contrast_ratio(colors.cover_text_color, shade) < MIN_UI_CONTRAST:
                    problems.append(f"cover text {colors.cover_text_color} on cover {shade} below {MIN_UI_CONTRAST}:1")
    if problems:
        return problems  # contrast math needs parseable colors
    for label, fg, bg, minimum in CONTRAST_PAIRS:
        ratio = contrast_ratio(getattr(colors, fg), getattr(colors, bg))
        if ratio < minimum:
            problems.append(f"{label} ({fg} on {bg}) contrast {ratio:.2f}:1 < {minimum}:1")
    return problems


_current = BROADSHEET


_PACKAGE_COLORS: dict[str, ThemeColors] = {}


def colors_for(name: str) -> ThemeColors:
    """ThemeColors for a saved theme value: one of the original seven, or a theme package added later (it gets the
    default structure and type options with its own colours, so a new package needs no code). Unknown -> the default."""
    if name in THEMES:
        return THEMES[name]
    from smartdoc.presentation.theme_manager import TOKEN_KEY_FOR_THEME, load_tokens, token_key_for

    token_key = token_key_for(name)
    original = next((saved for saved, tid in TOKEN_KEY_FOR_THEME.items() if tid == token_key), None)
    if original in THEMES:  # an unknown value resolves to the default theme, which is one of the seven
        return THEMES[original]
    if token_key not in _PACKAGE_COLORS:
        base = dataclasses.replace(THEMES[DEFAULT_THEME_KEY], key=token_key.replace("-", "_"), display_name=str(load_tokens()[token_key]["name"]))
        _PACKAGE_COLORS[token_key] = _with_tokens(base, load_tokens()[token_key])
    return _PACKAGE_COLORS[token_key]


def current_colors() -> ThemeColors:
    """Colors for the theme applied by the most recent apply_theme() call."""
    return _current


def apply_theme(app: QApplication, name: str, tokens: dict | None = None) -> ThemeColors:
    """`tokens`: the composed tokens of the applied layout + theme (ThemeManager.tokens()); the ThemeColors then carry
    the layout's retuned colours too, so widgets that still read ThemeColors match the ones ThemeManager styles."""
    global _current
    colors = colors_for(name)
    if tokens is not None:
        colors = _with_tokens(colors, tokens)
    _current = colors

    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(colors.background))
    palette.setColor(QPalette.WindowText, QColor(colors.sidebar_text))
    # Base/AlternateBase is what a plain QAbstractItemView paints as its own
    # background -- using content_bg here (not background/surface) is what
    # keeps the library grid/list light on Inky Night even though the rest
    # of the chrome is dark, without needing a second live QPalette.
    palette.setColor(QPalette.Base, QColor(colors.content_bg))
    palette.setColor(QPalette.AlternateBase, QColor(colors.content_bg))
    palette.setColor(QPalette.Text, QColor(colors.text))
    palette.setColor(QPalette.ToolTipBase, QColor(colors.surface))
    palette.setColor(QPalette.ToolTipText, QColor(colors.sidebar_text))
    palette.setColor(QPalette.Button, QColor(colors.surface))
    palette.setColor(QPalette.ButtonText, QColor(colors.sidebar_text))
    palette.setColor(QPalette.PlaceholderText, QColor(colors.muted_text))
    palette.setColor(QPalette.Highlight, QColor(colors.accent))
    palette.setColor(QPalette.HighlightedText, QColor(colors.accent_text))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors.muted_text))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors.muted_text))
    app.setPalette(palette)
    return colors


def apply_light_theme(app: QApplication) -> None:
    """Kept for the module demos that only ever want a plain default theme."""
    apply_theme(app, "broadsheet")


# -- Helpers widgets use to apply the style options ---------------------------


def qt_weight(css_weight: int) -> QFont.Weight:
    return QFont.Weight(max(100, min(900, int(css_weight))))


def theme_font(colors: ThemeColors | None = None, base: QFont | None = None) -> QFont:
    """The theme's app font (family fallback list, weight, spacing), at
    `base`'s size if given."""
    colors = colors or current_colors()
    font = QFont(base) if base is not None else QFont()
    font.setFamilies(list(colors.font_families))
    font.setWeight(qt_weight(colors.font_weight))
    if colors.letter_spacing != 100.0:
        font.setLetterSpacing(QFont.PercentageSpacing, colors.letter_spacing)
    return font


def resolve_font_family(colors: ThemeColors | None = None) -> str:
    """The family Qt will actually render `colors`' font stack with: the
    first one that's installed (case-insensitively), else the stack's first
    name. What Settings shows in its font pickers for a theme that has no
    user-chosen override."""
    colors = colors or current_colors()
    installed = {name.casefold(): name for name in QFontDatabase.families()}
    for name in colors.font_families:
        if name.casefold() in installed:
            return installed[name.casefold()]
    return colors.font_families[0]


def _snake(text: str) -> str:
    return "_".join(text.lower().split())


def section_text(text: str, colors: ThemeColors | None = None) -> str:
    """A section heading as the theme writes it: "BỘ SƯU TẬP" normally,
    "// bộ_sưu_tập" in the code label style."""
    colors = colors or current_colors()
    if colors.label_style == "code":
        return f"// {_snake(text)}"
    return text.upper()


def item_text(text: str, colors: ThemeColors | None = None) -> str:
    """A system/collection name as displayed (never changes stored data)."""
    colors = colors or current_colors()
    return _snake(text) if colors.label_style == "code" else text


_LEADING_SYMBOLS = re.compile(r"^[^\w\[]+", re.UNICODE)


def action_text(text: str, colors: ThemeColors | None = None) -> str:
    """A clickable action's label in the theme's style: "[ tạo tóm tắt ai ]"
    (bracket), plain words without a leading icon (link), or unchanged."""
    colors = colors or current_colors()
    if colors.action_style == "bracket":
        return f"[ {_LEADING_SYMBOLS.sub('', text).strip().lower()} ]"
    if colors.action_style == "link":
        return _LEADING_SYMBOLS.sub("", text).strip()
    return text


def action_css(colors: ThemeColors | None = None, *, font_px: int = 14) -> str:
    """Stylesheet body for an action label/button in the theme's style."""
    colors = colors or current_colors()
    if colors.action_style == "link":
        return (f"color: {colors.accent}; font-size: {font_px}px; background: transparent; border: none;"
                f" border-bottom: 1px solid {colors.accent}; padding: 0 0 2px 0;")
    if colors.action_style == "bracket":
        return (f"color: {colors.accent}; font-size: {font_px}px; background: transparent;"
                f" border: 1px solid {colors.accent}; border-radius: 0; padding: 7px 12px;")
    if colors.action_style == "soft":
        return (f"color: {colors.accent}; font-size: {font_px}px; background: rgba(95,214,196,.06);"
                f" border: 1px solid {colors.border}; border-radius: 8px; padding: 10px 14px;")
    return f"color: {colors.accent}; font-size: {font_px}px;"


def app_stylesheet(colors: ThemeColors) -> str:
    """Global stylesheet for themes whose buttons differ from Qt's own
    look. Empty for the original themes, so they render exactly as before."""
    if colors.action_style == "default" and colors.control_radius == 3:
        return ""
    if colors.action_style == "link":
        button = (f"QPushButton {{ background: transparent; color: {colors.accent}; border: none;"
                  f" border-bottom: 1px solid {colors.accent}; padding: 4px 2px; }}"
                  f" QPushButton:disabled {{ color: {colors.muted_text}; border-bottom-color: {colors.border}; }}")
    elif colors.action_style == "bracket":
        button = (f"QPushButton {{ background: transparent; color: {colors.accent}; border: 1px solid {colors.accent};"
                  f" border-radius: 0; padding: 5px 12px; }}"
                  f" QPushButton:hover {{ background: {colors.selected_bg}; }}"
                  f" QPushButton:disabled {{ color: {colors.muted_text}; border-color: {colors.border}; }}")
    else:
        radius = min(colors.control_radius, 10)
        button = (f"QPushButton {{ background: {colors.surface}; color: {colors.sidebar_text};"
                  f" border: 1px solid {colors.border}; border-radius: {radius}px; padding: 6px 14px; }}"
                  f" QPushButton:hover {{ border-color: {colors.accent}; color: {colors.accent}; }}"
                  f" QPushButton:disabled {{ color: {colors.muted_text}; }}")
    return button + f" QToolTip {{ background: {colors.surface}; color: {colors.sidebar_text}; border: 1px solid {colors.border}; }}"
