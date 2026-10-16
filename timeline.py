# -*- coding: utf-8 -*-
"""自绘时间轴:缩略图底、已收藏片段渐变带、入/出点标记、发光播放头、悬停时间气泡。
配色由 theme.timeline_colors() 提供,applyTheme() 切换。"""
from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (QPainter, QColor, QLinearGradient, QPainterPath, QPen,
                           QPolygonF, QFontMetrics)
from PySide6.QtWidgets import QWidget

from workers import fmt_ms
from theme import timeline_colors, DEFAULT_THEME


def _qc(spec) -> QColor:
    """'#rrggbb' 或 ('#rrggbb', alpha) → QColor。"""
    if isinstance(spec, tuple):
        c = QColor(spec[0])
        c.setAlpha(spec[1])
        return c
    return QColor(spec)


class Timeline(QWidget):
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(96)
        self.setCursor(Qt.PointingHandCursor)
        self._dur = 0
        self._pos = 0
        self._segs = []           # [(start_ms, end_ms)]
        self._pin = None
        self._pout = None
        self._thumbs = {}         # index -> QPixmap
        self._n = 0
        self._hover_x = None
        self.applyTheme(DEFAULT_THEME)

    # ---- 主题 ----
    def applyTheme(self, key):
        t = timeline_colors(key)
        self.c_bg = _qc(t["bg"])
        self.c_border = _qc(t["border"])
        self.c_seg1 = _qc(t["seg1"])
        self.c_seg2 = _qc(t["seg2"])
        self.c_seg_edge = _qc(t["seg_edge"])
        self.c_pending = _qc(t["pending"])
        self.c_tri = _qc(t["tri"])
        self.c_chip_bg = _qc(t["chip_bg"])
        self.c_chip_txt = _qc(t["chip_txt"])
        self.c_bubble_bg = _qc(t["bubble_bg"])
        self.c_bubble_border = _qc(t["bubble_border"])
        self.c_bubble_txt = _qc(t["bubble_txt"])
        self.c_empty_txt = _qc(t["empty_txt"])
        self.update()

    # ---- 外部接口 ----
    def setDuration(self, ms):
        self._dur = max(0, ms)
        self.update()

    def setPosition(self, ms):
        self._pos = ms
        self.update()

    def setSegments(self, segs):
        self._segs = list(segs)
        self.update()

    def setPending(self, pin, pout):
        self._pin, self._pout = pin, pout
        self.update()

    def setThumbCount(self, n):
        self._n = n
        self.update()

    def addThumb(self, i, pixmap):
        self._thumbs[i] = pixmap
        self.update()

    def reset(self):
        self._dur = self._pos = 0
        self._segs = []
        self._pin = self._pout = None
        self._thumbs = {}
        self._n = 0
        self.update()

    # ---- 坐标换算 ----
    def _bar(self) -> QRectF:
        return QRectF(self.rect().adjusted(10, 20, -10, -6))

    def _t2x(self, t, r: QRectF) -> float:
        if self._dur <= 0:
            return r.left()
        return r.left() + (t / self._dur) * r.width()

    def _x2t(self, x, r: QRectF) -> int:
        if self._dur <= 0 or r.width() <= 0:
            return 0
        frac = min(1.0, max(0.0, (x - r.left()) / r.width()))
        return int(frac * self._dur)

    # ---- 交互 ----
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._dur > 0:
            self.seekRequested.emit(self._x2t(e.position().x(), self._bar()))

    def mouseMoveEvent(self, e):
        self._hover_x = e.position().x()
        if e.buttons() & Qt.LeftButton and self._dur > 0:
            self.seekRequested.emit(self._x2t(self._hover_x, self._bar()))
        self.update()

    def leaveEvent(self, e):
        self._hover_x = None
        self.update()

    # ---- 绘制 ----
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self._bar()
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, self.c_bg)

        p.save()
        p.setClipPath(path)
        if self._n and self._thumbs:
            slot = r.width() / self._n
            for i, pix in self._thumbs.items():
                target = QRectF(r.left() + i * slot, r.top(), slot + 1.0, r.height())
                p.drawPixmap(target.toRect(), pix)
            shade = QLinearGradient(0, r.top(), 0, r.bottom())
            shade.setColorAt(0.0, QColor(0, 0, 0, 70))
            shade.setColorAt(0.35, QColor(0, 0, 0, 0))
            shade.setColorAt(1.0, QColor(0, 0, 0, 90))
            p.fillPath(path, shade)
        elif self._dur <= 0:
            p.setPen(self.c_empty_txt)
            p.drawText(r, Qt.AlignCenter, "· · · 时间轴 · · ·")

        if self._dur > 0:
            for idx, (s, e_ms) in enumerate(self._segs, 1):
                self._draw_band(p, r, s, e_ms, self.c_seg1, self.c_seg2,
                                self.c_seg_edge, solid=True, num=idx)
            if self._pin is not None and self._pout is not None:
                a = QColor(self.c_pending)
                a.setAlpha(70)
                self._draw_band(p, r, min(self._pin, self._pout),
                                max(self._pin, self._pout), a, a,
                                self.c_pending, solid=False)
            else:
                if self._pin is not None:
                    self._draw_flag(p, r, self._pin, "I")
                if self._pout is not None:
                    self._draw_flag(p, r, self._pout, "O")
        p.restore()

        p.strokePath(path, QPen(self.c_border, 1))

        if self._dur > 0:
            self._draw_playhead(p, r)
        if self._hover_x is not None and self._dur > 0:
            self._draw_bubble(p, r)

    def _draw_band(self, p, r, s, e, c1, c2, edge, solid, num=None):
        x1, x2 = self._t2x(s, r), self._t2x(e, r)
        band = QRectF(x1, r.top() + 1.5, max(3.0, x2 - x1), r.height() - 3)
        g = QLinearGradient(band.left(), 0, band.right(), 0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        bp = QPainterPath()
        bp.addRoundedRect(band, 4, 4)
        p.fillPath(bp, g)
        pen = QPen(edge, 2.0 if solid else 1.4)
        if not solid:
            pen.setStyle(Qt.DashLine)
        p.strokePath(bp, pen)      # 只描边;drawPath 会带上残留画刷把色带填死
        if num is not None and band.width() > 24:
            chip = QRectF(band.left() + 3, band.top() + 3, 16, 14)
            p.setPen(Qt.NoPen)
            p.setBrush(self.c_chip_bg)
            p.drawRoundedRect(chip, 4, 4)
            f = p.font()
            f.setBold(True)
            f.setPixelSize(10)
            p.setFont(f)
            p.setPen(self.c_chip_txt)
            p.drawText(chip, Qt.AlignCenter, str(num))
            p.setBrush(Qt.NoBrush)

    def _draw_flag(self, p, r, t, label):
        x = self._t2x(t, r)
        p.setPen(QPen(self.c_pending, 2))
        p.drawLine(QPointF(x, r.top() + 1), QPointF(x, r.bottom() - 1))
        tag = QRectF(x - 9, r.top() + 3, 18, 15)
        p.setPen(Qt.NoPen)
        p.setBrush(self.c_pending)
        p.drawRoundedRect(tag, 4, 4)
        p.setPen(QColor("#1a1205"))
        f = p.font()
        f.setBold(True)
        f.setPixelSize(11)
        p.setFont(f)
        p.drawText(tag, Qt.AlignCenter, label)
        p.setBrush(Qt.NoBrush)

    def _draw_playhead(self, p, r):
        x = self._t2x(min(self._pos, self._dur), r)
        p.setPen(QPen(QColor(255, 255, 255, 45), 6))
        p.drawLine(QPointF(x, r.top() - 2), QPointF(x, r.bottom() + 2))
        p.setPen(QPen(QColor("#f5f9ff"), 2))
        p.drawLine(QPointF(x, r.top() - 2), QPointF(x, r.bottom() + 2))
        tri = QPolygonF([QPointF(x - 5, r.top() - 9), QPointF(x + 5, r.top() - 9),
                         QPointF(x, r.top() - 1)])
        p.setPen(Qt.NoPen)
        p.setBrush(self.c_tri)
        p.drawPolygon(tri)
        p.setBrush(Qt.NoBrush)

    def _draw_bubble(self, p, r):
        t = self._x2t(self._hover_x, r)
        text = fmt_ms(t)
        f = p.font()
        f.setBold(False)
        f.setPixelSize(11)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(text) + 14
        x = min(max(self._hover_x - w / 2, 2), self.width() - w - 2)
        box = QRectF(x, 1, w, 17)
        p.setPen(QPen(self.c_bubble_border, 1))
        p.setBrush(self.c_bubble_bg)
        p.drawRoundedRect(box, 6, 6)
        p.setPen(self.c_bubble_txt)
        p.setBrush(Qt.NoBrush)
        p.drawText(box, Qt.AlignCenter, text)
