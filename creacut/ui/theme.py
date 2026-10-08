"""CREA brand theme: light/dark palettes, QSS builders and the live toggle.

The five CREA brand hues (magenta, purple, cyan, yellow, plus black/white)
never change between modes — only the *structural* roles (backgrounds,
borders, muted text, scrollbars, notices) are swapped, so switching modes
never dilutes brand recognition. Contrast rule inherited from the previous
single-theme module: white/black text on magenta, purple and cyan pass WCAG
AA (>=4.5:1) EXCEPT white text on cyan (2.78:1, fails) — cyan therefore only
ever pairs with black text (frame_text), in both modes.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QSettings, Signal

_MODE_SETTINGS_KEY = "ui/themeMode"

# Brand hues: identical in both modes, this is what keeps the UI "looking
# like CREA" regardless of light/dark.
BRAND = {
    "accent": "#C8238D",         # CREA magenta -- primary actions, CTAs, focus
    "accent_hover": "#8B1967",   # CREA purple -- hover/pressed depth on accent
    "accent_text": "#ffffff",
    "frame": "#00A9CE",          # CREA cyan -- frame/selection accent
    "frame_text": "#000000",     # mandatory pairing for any frame fill
    "keep_highlight": "#F5E600", # CREA yellow -- "Conservar" / positive highlight
    "keep_highlight_hover": "#E0C400",
    "keep_highlight_text": "#1a1a1a",
    "button_pressed": "#6f1452",
    "danger": "#c62828",
    "danger_hover": "#a91f1f",
}

LIGHT = {
    "bg": "#ffffff",
    "surface": "#f7f2f9",
    "surface_alt": "#efe0f1",
    "input_bg": "#ffffff",
    "border": "#cdb6d4",
    "border_soft": "#ecdff0",
    "text": "#221527",
    "text_muted": "#7a6483",
    "disabled_bg": "#f2ebf4",
    "disabled_text": "#b39dbb",
    "scrollbar_handle": "#c9aed1",
    "tab_hover": "#f3d9ec",
    "ink_cyan": "#046579",          # dark cyan-family ink, readable on light bg
    "region_keep_manual": "#0b6d7e",
    "warning_bg": "#fff3cd",
    "warning_text": "#664d03",
    "warning_border": "#ffecb5",
    "danger_notice_bg": "#f8d7da",
    "danger_notice_text": "#842029",
    "danger_notice_border": "#f5c2c7",
}

DARK = {
    "bg": "#140f19",
    "surface": "#1e1524",
    "surface_alt": "#2a1e33",
    "input_bg": "#241a2c",
    "border": "#4a3657",
    "border_soft": "#3a2a44",
    "text": "#f3ecf5",
    "text_muted": "#b39ec0",
    "disabled_bg": "#241a2c",
    "disabled_text": "#6b5b73",
    "scrollbar_handle": "#5b4468",
    "tab_hover": "#3a2030",
    "ink_cyan": "#5fd8f0",           # light cyan-family ink, readable on dark bg
    "region_keep_manual": "#3fa8bd",
    "warning_bg": "#4a3b12",
    "warning_text": "#ffe27a",
    "warning_border": "#6b5518",
    "danger_notice_bg": "#4a1f22",
    "danger_notice_text": "#ffb4b4",
    "danger_notice_border": "#6b2b2f",
}


class _ThemeBus(QObject):
    changed = Signal(str)


bus = _ThemeBus()
_mode = QSettings().value(_MODE_SETTINGS_KEY, "light", type=str)
if _mode not in ("light", "dark"):
    _mode = "light"


def get_mode() -> str:
    return _mode


def set_mode(mode: str) -> None:
    global _mode
    if mode not in ("light", "dark"):
        raise ValueError(f"unknown theme mode: {mode!r}")
    if mode == _mode:
        return
    _mode = mode
    QSettings().setValue(_MODE_SETTINGS_KEY, mode)
    bus.changed.emit(mode)


def toggle_mode() -> None:
    set_mode("dark" if _mode == "light" else "light")


def palette(mode: str | None = None) -> dict[str, str]:
    structural = DARK if (mode or _mode) == "dark" else LIGHT
    return {**BRAND, **structural}


def current_palette() -> dict[str, str]:
    return palette(_mode)


def build_stylesheet(c: dict[str, str]) -> str:
    """Main EditorWindow stylesheet."""
    return f"""
QMainWindow, QDialog {{
    background: {c['bg']};
}}
QWidget#editorCentral {{
    background: {c['bg']};
}}
QLabel {{
    color: {c['text']};
    background: transparent;
    selection-background-color: {c['accent']};
    selection-color: {c['accent_text']};
}}
QMenuBar {{
    background: {c['surface']};
    color: {c['text']};
    border-bottom: 2px solid {c['frame']};
}}
QMenuBar::item:selected {{
    background: {c['accent']};
    color: {c['accent_text']};
}}
QMenu {{
    background: {c['bg']};
    color: {c['text']};
    border: 1px solid {c['border']};
}}
QMenu::separator {{
    height: 1px;
    background: {c['border_soft']};
    margin: 4px 6px;
}}
QMenu::item:selected {{
    background: {c['accent']};
    color: {c['accent_text']};
}}
QStatusBar {{
    background: {c['surface']};
    color: {c['text_muted']};
}}
QDockWidget {{
    color: {c['text']};
}}
QDockWidget::title {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['surface']}, stop:1 {c['surface_alt']});
    color: {c['accent_hover']};
    font-weight: 600;
    padding: 6px 8px;
    border-bottom: 2px solid {c['frame']};
}}
QPushButton {{
    background: {c['accent_hover']};
    color: {c['accent_text']};
    border: 1px solid {c['button_pressed']};
    border-radius: 4px;
    padding: 6px 12px;
    min-height: 20px;
}}
QPushButton:hover {{
    background: {c['accent']};
    border-color: {c['accent_hover']};
}}
QPushButton:pressed {{
    background: {c['button_pressed']};
}}
QPushButton:disabled {{
    background: {c['disabled_bg']};
    color: {c['disabled_text']};
    border-color: {c['border_soft']};
}}
QPushButton:default {{
    background: {c['accent']};
    color: {c['accent_text']};
    border-color: {c['accent_hover']};
}}
QPushButton:default:hover {{
    background: {c['accent_hover']};
}}
QPushButton[class="success"] {{
    background: {c['keep_highlight']};
    color: {c['keep_highlight_text']};
    border-color: {c['keep_highlight_hover']};
}}
QPushButton[class="success"]:hover {{
    background: {c['keep_highlight_hover']};
}}
QPushButton[class="danger"] {{
    background: {c['danger']};
    color: #ffffff;
    border-color: {c['danger_hover']};
}}
QPushButton[class="danger"]:hover {{
    background: {c['danger_hover']};
}}
QPushButton#themeToggleButton {{
    background: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 17px;
    padding: 0px;
    font-size: 16px;
    min-height: 0;
}}
QPushButton#themeToggleButton:hover {{
    border-color: {c['frame']};
}}
QPushButton#themeToggleButton:checked {{
    background: {c['accent_hover']};
    color: {c['accent_text']};
    border-color: {c['accent']};
}}
QComboBox, QLineEdit, QTextEdit {{
    background: {c['input_bg']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 3px 6px;
    selection-background-color: {c['accent']};
    selection-color: {c['accent_text']};
}}
QComboBox:focus, QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid {c['frame']};
}}
QComboBox QAbstractItemView {{
    background: {c['input_bg']};
    color: {c['text']};
    selection-background-color: {c['accent']};
    selection-color: {c['accent_text']};
}}
QListWidget, QTableWidget {{
    background: {c['input_bg']};
    alternate-background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    gridline-color: {c['border_soft']};
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background: {c['frame']};
    color: {c['frame_text']};
}}
QTabWidget::pane {{
    border: 1px solid {c['border']};
    background: {c['bg']};
}}
QTabBar::tab {{
    background: {c['surface_alt']};
    color: {c['text_muted']};
    border: 1px solid {c['border']};
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
    padding: 7px 12px;
}}
QTabBar::tab:hover {{
    background: {c['tab_hover']};
    color: {c['text']};
}}
QTabBar::tab:selected {{
    background: {c['frame']};
    color: {c['frame_text']};
    font-weight: 600;
}}
QLabel#transcriptHint, QLabel#scriptHint {{
    color: {c['text_muted']};
    padding: 2px 2px 6px;
}}
QHeaderView::section {{
    background: {c['surface_alt']};
    color: {c['text']};
    padding: 4px;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 2px solid {c['frame']};
}}
QSlider::groove:horizontal {{
    background: {c['surface_alt']};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']};
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: 2px;
}}
QScrollArea#sourceTimelineScroll {{
    background: {c['bg']};
    border: 2px solid {c['frame']};
    border-radius: 4px;
}}
QScrollArea#sourceTimelineScroll > QWidget > QWidget {{
    background: {c['bg']};
}}
QScrollBar:horizontal {{
    background: {c['surface']};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c['scrollbar_handle']};
    min-width: 24px;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c['accent']};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QScrollBar:vertical {{
    background: {c['surface']};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['scrollbar_handle']};
    min-height: 24px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
"""


def build_start_stylesheet(c: dict[str, str]) -> str:
    """StartWindow stylesheet."""
    return f"""
QMainWindow, QDialog {{
    background: {c['bg']};
}}
QLabel {{
    color: {c['text']};
    background: transparent;
}}
QLabel[class="muted"] {{
    color: {c['text_muted']};
}}
QPushButton {{
    background: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 6px 12px;
}}
QPushButton:hover {{
    background: {c['tab_hover']};
    border-color: {c['frame']};
}}
QPushButton:pressed {{
    background: {c['border_soft']};
}}
QPushButton:disabled {{
    background: {c['disabled_bg']};
    color: {c['disabled_text']};
    border-color: {c['border_soft']};
}}
QPushButton:default {{
    background: {c['accent']};
    color: {c['accent_text']};
    border-color: {c['accent_hover']};
}}
QPushButton:default:hover {{
    background: {c['accent_hover']};
}}
QPushButton#themeToggleButton {{
    background: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 17px;
    padding: 0px;
    font-size: 16px;
}}
QPushButton#themeToggleButton:hover {{
    border-color: {c['frame']};
}}
QPushButton#themeToggleButton:checked {{
    background: {c['accent_hover']};
    color: {c['accent_text']};
    border-color: {c['accent']};
}}
QLineEdit {{
    background: {c['input_bg']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 3px 6px;
}}
QLineEdit:focus {{
    border: 2px solid {c['frame']};
}}
QStatusBar {{
    background: {c['surface_alt']};
    color: {c['text_muted']};
}}
"""


def resume_banner_style(c: dict[str, str]) -> str:
    return (
        f"QFrame {{ background: {c['surface_alt']}; border: 1px solid {c['frame']}; "
        "border-radius: 4px; }"
        f"QFrame QLabel {{ color: {c['text']}; background: transparent; }}"
        "QFrame QPushButton#resumeContinueButton {"
        f"  color: {c['accent_text']}; background: {c['accent']};"
        f"  border: 1px solid {c['accent_hover']}; border-radius: 3px; padding: 4px 10px; }}"
        "QFrame QPushButton#resumeContinueButton:hover {"
        f"  background: {c['accent_hover']}; }}"
        "QFrame QPushButton#resumeDismissButton {"
        f"  color: {c['text']}; background: {c['input_bg']}; border: 1px solid {c['frame']};"
        "  border-radius: 3px; padding: 4px 10px; }"
        "QFrame QPushButton#resumeDismissButton:hover {"
        f"  background: {c['tab_hover']}; }}"
    )


def warning_notice_style(c: dict[str, str]) -> str:
    return (
        f"QLabel {{ background: {c['warning_bg']}; color: {c['warning_text']}; padding: 7px; "
        f"border: 1px solid {c['warning_border']}; border-radius: 3px; }}"
    )


def danger_notice_style(c: dict[str, str]) -> str:
    return (
        f"QLabel {{ background: {c['danger_notice_bg']}; color: {c['danger_notice_text']}; padding: 7px; "
        f"border: 1px solid {c['danger_notice_border']}; border-radius: 3px; }}"
    )


def timeline_colors(c: dict[str, str]) -> dict[str, str]:
    return {
        "bg": c["bg"],
        "empty_text": c["text_muted"],
        "ruler_bg": c["surface_alt"],
        "ruler_line": c["text_muted"],
        "thumb_bg": c["surface"],
        "thumb_placeholder": c["text_muted"],
        "wave_bg": c["surface_alt"],
        "wave_baseline": c["border"],
        "wave_fill": c["ink_cyan"],
        "wave_placeholder": c["text_muted"],
        "region_border": c["text"],
        "region_keep_auto": c["frame"],
        "region_keep_manual": c["region_keep_manual"],
        "region_keep_text": c["frame_text"],
        "region_discard_auto": c["accent"],
        "region_discard_manual": c["accent_hover"],
        "region_discard_text": c["accent_text"],
        "selection_outline": c["keep_highlight"],
        "playhead": c["danger"],
        "footer_text": c["text_muted"],
    }
