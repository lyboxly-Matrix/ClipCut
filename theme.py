# -*- coding: utf-8 -*-
"""主题系统:调色板 + QSS 模板。三套主题:霓虹青紫(默认)/ 黑曜石 / Copilot 渐变。
注意:控件不用 setFixedHeight+padding 组合,统一 min-height 防裁字。"""
from string import Template

# key -> (显示名, 调色板)
THEMES = {
    "neon": ("霓虹", {
        "root": "#0b0d13", "panel": "#10141d", "card": "#151b29", "card_hover": "#1a2233",
        "video_bg": "#05060a", "sb_bg": "#0e1118",
        "b1": "#232a3a", "b2": "#2a3244", "b3": "#3b465e",
        "txt": "#cdd6e4", "txt_bright": "#e6ecf5", "txt_dim": "#8b94a7",
        "txt_faint": "#4f5870", "txt_hint": "#6b7385", "txt_status": "#5b6478",
        "accent": "#22d3ee", "accent2": "#a78bfa",
        "btn_bg": "#1a2030", "btn_hover": "#232b40", "btn_pressed": "#151a28",
        "grad_primary": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #06b6d4, stop:1 #8b5cf6)",
        "grad_primary_hover": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #22d3ee, stop:1 #a78bfa)",
        "grad_check": "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #06b6d4, stop:1 #8b5cf6)",
        "primary_txt": "white",
        "mark_c": "#fbbf24", "mark_b": "#4a3b1a", "mark_hbg": "#2b2416",
        "mark_hb": "#7a601f", "mark_hc": "#fcd34d",
        "add_c": "#67e8f9", "add_b": "#164e5e", "add_hbg": "#0e2a35", "add_hb": "#1a7a94",
        "handle": "#e6ecf5",
    }),
    "obsidian": ("黑曜石", {
        "root": "#050607", "panel": "#0b0c0e", "card": "#101214", "card_hover": "#16181b",
        "video_bg": "#000000", "sb_bg": "#08090b",
        "b1": "#1c1f24", "b2": "#24282e", "b3": "#3a3f47",
        "txt": "#d6d9de", "txt_bright": "#f2f4f7", "txt_dim": "#8e939b",
        "txt_faint": "#565c66", "txt_hint": "#6f757e", "txt_status": "#61666e",
        "accent": "#e8c15a", "accent2": "#f5d78e",
        "btn_bg": "#131518", "btn_hover": "#1d2025", "btn_pressed": "#0d0f11",
        "grad_primary": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #a97c22, stop:1 #e8c15a)",
        "grad_primary_hover": "qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #c99733, stop:1 #f5d78e)",
        "grad_check": "qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #a97c22, stop:1 #e8c15a)",
        "primary_txt": "#1a1205",
        "mark_c": "#e8c15a", "mark_b": "#4a3b1a", "mark_hbg": "#241d0e",
        "mark_hb": "#8a6a1f", "mark_hc": "#f5d78e",
        "add_c": "#e5e7eb", "add_b": "#3a3f47", "add_hbg": "#1d2025", "add_hb": "#565c66",
        "handle": "#f2f4f7",
    }),
    "copilot": ("Copilot", {
        "root": "#141319", "panel": "#1c1b22", "card": "#232230", "card_hover": "#2a2938",
        "video_bg": "#0a0a0f", "sb_bg": "#18171e",
        "b1": "#2e2d3a", "b2": "#343247", "b3": "#45435a",
        "txt": "#d5d3e0", "txt_bright": "#f4f3fa", "txt_dim": "#918fa5",
        "txt_faint": "#5b5970", "txt_hint": "#767490", "txt_status": "#6b6980",
        "accent": "#7a8cf8", "accent2": "#e9578c",
        "btn_bg": "#232230", "btn_hover": "#2c2b3d", "btn_pressed": "#1a1926",
        "grad_primary": ("qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #38c3f5,"
                         " stop:0.35 #5b6cf2, stop:0.7 #a552e0, stop:1 #e9578c)"),
        "grad_primary_hover": ("qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #55d2fd,"
                               " stop:0.35 #7583fa, stop:0.7 #b96ee9, stop:1 #f272a2)"),
        "grad_check": ("qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #38c3f5,"
                       " stop:0.5 #a552e0, stop:1 #e9578c)"),
        "primary_txt": "white",
        "mark_c": "#f6a356", "mark_b": "#4d3520", "mark_hbg": "#2b2118",
        "mark_hb": "#8a5c2c", "mark_hc": "#fcc389",
        "add_c": "#38c3f5", "add_b": "#1c4d63", "add_hbg": "#132734", "add_hb": "#2a7ea0",
        "handle": "#f4f3fa",
    }),
}

DEFAULT_THEME = "neon"

# 时间轴自绘控件的配色:hex 或 (hex, alpha)
TIMELINE_COLORS = {
    "neon": {
        "bg": "#0f1420", "border": "#262d3d",
        "seg1": ("#22d3ee", 115), "seg2": ("#a78bfa", 115), "seg_edge": ("#67e8f9", 235),
        "pending": "#f59e0b", "tri": "#22d3ee",
        "chip_bg": "#0b0d13", "chip_txt": "#67e8f9",
        "bubble_bg": "#1a2030", "bubble_border": "#3b465e", "bubble_txt": "#cdd6e4",
        "empty_txt": "#3c4454",
    },
    "obsidian": {
        "bg": "#0a0b0d", "border": "#24282e",
        "seg1": ("#e8c15a", 105), "seg2": ("#a97c22", 105), "seg_edge": ("#f0cd78", 235),
        "pending": "#f2f4f7", "tri": "#e8c15a",
        "chip_bg": "#050607", "chip_txt": "#e8c15a",
        "bubble_bg": "#131518", "bubble_border": "#3a3f47", "bubble_txt": "#d6d9de",
        "empty_txt": "#464c55",
    },
    "copilot": {
        "bg": "#16151c", "border": "#2e2d3a",
        "seg1": ("#38c3f5", 110), "seg2": ("#e9578c", 110), "seg_edge": ("#8f8ff7", 235),
        "pending": "#f6a356", "tri": "#38c3f5",
        "chip_bg": "#141319", "chip_txt": "#9aa8ff",
        "bubble_bg": "#232230", "bubble_border": "#45435a", "bubble_txt": "#d5d3e0",
        "empty_txt": "#4a485e",
    },
}

_TEMPLATE = Template("""
* { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; font-size: 13px; }

QMainWindow, QWidget#Root { background: $root; }
QDialog, QMessageBox { background: $panel; color: $txt; }
QMessageBox QLabel { color: $txt; }

QLabel { color: $txt; background: transparent; }
QLabel#Logo { font-size: 19px; font-weight: 700; color: $accent; }
QLabel#Sub { color: $txt_hint; font-size: 13px; }
QLabel#FileLabel { color: $txt_dim; }
QLabel#Time { font-family: Consolas, monospace; font-size: 14px; color: $txt_dim; }
QLabel#H1 { font-size: 15px; font-weight: 700; color: $txt_bright; }
QLabel#H2 { font-size: 12px; font-weight: 600; color: $txt_hint; margin-top: 4px; }
QLabel#Hint { color: $txt_faint; font-size: 11px; }
QLabel#Count { color: $accent; font-weight: 700; }
QLabel#SegTitle { font-weight: 700; color: $txt_bright; }
QLabel#SegTime { font-family: Consolas, monospace; color: $txt_dim; font-size: 12px; }
QLabel#DropIcon { font-size: 46px; }
QLabel#DropText { color: $txt_faint; font-size: 15px; }

QPushButton {
    background: $btn_bg; color: $txt;
    border: 1px solid $b2; border-radius: 8px;
    padding: 6px 14px; min-height: 22px;
}
QPushButton:hover { background: $btn_hover; border-color: $b3; color: $txt_bright; }
QPushButton:pressed { background: $btn_pressed; }
QPushButton:disabled { color: $txt_faint; background: $panel; border-color: $b1; }

QPushButton#Icon { font-size: 15px; padding: 4px 10px; min-width: 20px; }
QPushButton#Play { font-size: 17px; min-width: 34px; padding: 5px 12px; border-color: $b3; }
QPushButton#Mark { color: $mark_c; border-color: $mark_b; }
QPushButton#Mark:hover { background: $mark_hbg; border-color: $mark_hb; color: $mark_hc; }
QPushButton#Add { color: $add_c; border-color: $add_b; font-weight: 600; }
QPushButton#Add:hover { background: $add_hbg; border-color: $add_hb; }
QPushButton#Primary {
    background: $grad_primary;
    color: $primary_txt; font-weight: 700; font-size: 14px;
    border: none; border-radius: 10px; padding: 10px 16px;
}
QPushButton#Primary:hover { background: $grad_primary_hover; }
QPushButton#Primary:disabled { background: $b1; color: $txt_faint; }
QPushButton#Tiny, QPushButton#Del {
    padding: 2px 8px; min-height: 18px; font-size: 12px;
    background: transparent; border: 1px solid $b2; color: $txt_dim;
}
QPushButton#Tiny:hover { color: $txt_bright; border-color: $b3; background: $btn_hover; }
QPushButton#Del:hover { color: #f87171; border-color: #7f1d1d; background: #2a1515; }

QFrame#Side { background: $panel; border: 1px solid $b1; border-radius: 12px; }
QFrame#VideoBox { background: $video_bg; border: 1px solid $b1; border-radius: 12px; }
QFrame#DropHint { background: transparent; border: 2px dashed $b2; border-radius: 14px; }
QFrame#SegCard {
    background: $card; border: 1px solid $b2;
    border-left: 3px solid $accent; border-radius: 8px;
}
QFrame#SegCard:hover { background: $card_hover; border-color: $b3; }

QListWidget#SegList { background: transparent; border: none; outline: none; }
QListWidget#SegList::item { background: transparent; border: none; }
QListWidget#SegList::item:selected { background: transparent; }

QComboBox {
    background: $btn_bg; color: $txt; border: 1px solid $b2;
    border-radius: 8px; padding: 5px 10px; min-height: 22px;
}
QComboBox:hover { border-color: $b3; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid $txt_hint; margin-right: 8px;
}
QComboBox QAbstractItemView {
    background: $btn_bg; color: $txt; border: 1px solid $b2;
    selection-background-color: $btn_hover; selection-color: $accent;
    outline: none;
}

QCheckBox { color: $txt_dim; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid $b3; background: $btn_bg;
}
QCheckBox::indicator:checked { background: $grad_check; border-color: $accent; }

QSlider::groove:horizontal { height: 4px; background: $b2; border-radius: 2px; }
QSlider::sub-page:horizontal { background: $accent; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 12px; height: 12px; margin: -4px 0;
    border-radius: 6px; background: $handle;
}
QSlider::handle:horizontal:hover { background: $accent; }

QProgressBar {
    background: $btn_bg; border: 1px solid $b2; border-radius: 7px;
    text-align: center; color: $txt_bright; font-size: 11px; min-height: 14px;
}
QProgressBar::chunk { background: $grad_primary; border-radius: 6px; }

QStatusBar { background: $sb_bg; color: $txt_status; }
QStatusBar::item { border: none; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: $b2; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $b3; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QToolTip {
    background: $btn_bg; color: $txt; border: 1px solid $b3;
    border-radius: 6px; padding: 4px 8px;
}
""")


def build_qss(key: str) -> str:
    if key not in THEMES:
        key = DEFAULT_THEME
    return _TEMPLATE.substitute(THEMES[key][1])


def theme_label(key: str) -> str:
    return THEMES.get(key, THEMES[DEFAULT_THEME])[0]


def timeline_colors(key: str) -> dict:
    return TIMELINE_COLORS.get(key, TIMELINE_COLORS[DEFAULT_THEME])
