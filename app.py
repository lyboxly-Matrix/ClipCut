# -*- coding: utf-8 -*-
"""ClipCut 主窗口:播放器 + 打点 + 片段清单 + 导出。"""
import ctypes
import os
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, QTimer, QSettings, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QPixmap, QPainter, QColor, QLinearGradient, QIcon, QFont
from PySide6.QtWidgets import (QMainWindow, QWidget, QLabel, QPushButton, QVBoxLayout,
                               QHBoxLayout, QFileDialog, QListWidget, QListWidgetItem,
                               QFrame, QComboBox, QCheckBox, QSlider, QProgressBar,
                               QMessageBox, QStackedWidget, QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from timeline import Timeline
from theme import THEMES, DEFAULT_THEME, build_qss
from workers import find_tool, fmt_ms, ThumbnailWorker, ExportWorker
from crop import FrameWorker, CropDialog
from video_view import VideoView
from PySide6.QtGui import QImage

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
              ".ts", ".m4v", ".mpg", ".mpeg", ".rmvb", ".3gp"}
HINT = "Space 播放 · I/O 打点 · Enter 收藏 · ← → ±5s · , . 逐帧 · Esc 清除"


def make_app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    g = QLinearGradient(0, 0, 64, 64)
    g.setColorAt(0, QColor("#06b6d4"))
    g.setColorAt(1, QColor("#8b5cf6"))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI Emoji")
    f.setPixelSize(34)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "✂")
    p.end()
    return QIcon(pm)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ClipCut")
        self.setWindowIcon(make_app_icon())
        self.resize(1280, 760)
        self.setMinimumSize(1180, 640)
        self.setAcceptDrops(True)

        self.ffmpeg = find_tool("ffmpeg")
        self.settings = QSettings("ClipCut", "ClipCut")
        self.current = None
        self.segments = []            # [(start_ms, end_ms)]
        self.pending_in = None
        self.pending_out = None
        self.preview_end = None
        self.custom_outdir = None
        self.thumb_worker = None
        self.export_worker = None
        self.crop_worker = None
        self.crop_rect = None
        self._crop_previous_mode = 0
        self._processing_active = False
        self.thumb_dirs = []
        self._thumbs_started = False
        self._dark_titlebar_done = False

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)

        self._build_ui()
        self.player.setVideoOutput(self.video.item)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.errorOccurred.connect(self._on_error)

        self._install_shortcuts()
        for b in self.findChildren(QPushButton):
            b.setFocusPolicy(Qt.NoFocus)

        self._apply_theme(self.settings.value("theme", DEFAULT_THEME))

        if not self.ffmpeg:
            QTimer.singleShot(300, self._warn_no_ffmpeg)

    # ================= UI =================
    def _build_ui(self):
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(14, 12, 14, 8)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(10)
        outer.addLayout(left, 1)

        # -- 顶栏 --
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(QLabel("✂ ClipCut", objectName="Logo"))
        top.addStretch(1)
        self.lbl_file = QLabel("", objectName="FileLabel")
        self.lbl_file.setMaximumWidth(320)
        top.addWidget(self.lbl_file)
        self.btn_crop = QPushButton("裁剪画面")
        self.btn_crop.setToolTip("用鼠标框选要保留的画面，选择横屏、竖屏或方形比例")
        self.btn_crop.clicked.connect(self.edit_crop)
        top.addWidget(self.btn_crop)
        self.cmb_theme = QComboBox()
        for key, (label, _) in THEMES.items():
            self.cmb_theme.addItem(f"🎨 {label}", key)
        self.cmb_theme.setToolTip("主题")
        self.cmb_theme.currentIndexChanged.connect(
            lambda i: self._apply_theme(self.cmb_theme.itemData(i)))
        top.addWidget(self.cmb_theme)
        btn_open = QPushButton("📂", objectName="Icon")
        btn_open.setToolTip("打开视频 (Ctrl+O)")
        btn_open.clicked.connect(self.open_file)
        top.addWidget(btn_open)
        left.addLayout(top)

        # -- 视频区(空态提示 / 播放器) --
        box = QFrame(objectName="VideoBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(1, 1, 1, 1)
        self.stack = QStackedWidget()
        bl.addWidget(self.stack)

        hint = QFrame(objectName="DropHint")
        hl = QVBoxLayout(hint)
        hl.setAlignment(Qt.AlignCenter)
        ic = QLabel("🎬", objectName="DropIcon")
        ic.setAlignment(Qt.AlignCenter)
        tx = QLabel("拖入视频,或点 📂\n\nI 入点 → O 出点 → Enter 收藏", objectName="DropText")
        tx.setAlignment(Qt.AlignCenter)
        hl.addWidget(ic, 0, Qt.AlignHCenter)
        hl.addWidget(tx, 0, Qt.AlignHCenter)
        hint_wrap = QWidget()
        hw = QVBoxLayout(hint_wrap)
        hw.setContentsMargins(24, 24, 24, 24)
        hw.addWidget(hint)
        self.stack.addWidget(hint_wrap)

        self.video = VideoView()
        self.video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.stack.addWidget(self.video)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left.addWidget(box, 1)

        # -- 时间轴 --
        self.timeline = Timeline()
        self.timeline.seekRequested.connect(self.player.setPosition)
        left.addWidget(self.timeline)

        # -- 传输条 --
        tr = QHBoxLayout()
        tr.setSpacing(6)

        def icon_btn(text, tip, slot, name="Icon"):
            b = QPushButton(text, objectName=name)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            tr.addWidget(b)
            return b

        icon_btn("⏪", "后退 5 秒 (←)", lambda: self._jump(-5000))
        self.btn_play = icon_btn("▶", "播放/暂停 (Space)", self.toggle_play, "Play")
        icon_btn("⏩", "前进 5 秒 (→)", lambda: self._jump(5000))
        icon_btn("◁", "上一帧 (,)", lambda: self._jump(-40))
        icon_btn("▷", "下一帧 (.)", lambda: self._jump(40))

        self.lbl_time = QLabel("00:00:00.0 / 00:00:00.0", objectName="Time")
        tr.addSpacing(8)
        tr.addWidget(self.lbl_time)
        tr.addStretch(1)

        self.cmb_speed = QComboBox()
        self.cmb_speed.addItems(["0.5×", "0.75×", "1.0×", "1.25×", "1.5×", "2.0×"])
        self.cmb_speed.setCurrentIndex(2)
        self.cmb_speed.setToolTip("播放速度")
        self.cmb_speed.currentTextChanged.connect(
            lambda t: self.player.setPlaybackRate(float(t.rstrip("×"))))
        tr.addWidget(self.cmb_speed)

        tr.addWidget(QLabel("🔊"))
        vol = QSlider(Qt.Horizontal)
        vol.setFixedWidth(70)
        vol.setRange(0, 100)
        vol.setValue(80)
        vol.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        tr.addWidget(vol)
        tr.addSpacing(10)

        b_in = QPushButton("设为起点", objectName="Mark")
        b_in.setToolTip("将当前播放位置设为片段起点（快捷键 I）")
        b_in.clicked.connect(self.mark_in)
        tr.addWidget(b_in)
        b_out = QPushButton("设为终点", objectName="Mark")
        b_out.setToolTip("将当前播放位置设为片段终点（快捷键 O）")
        b_out.clicked.connect(self.mark_out)
        tr.addWidget(b_out)
        b_add = QPushButton("添加片段", objectName="Add")
        b_add.setToolTip("将起点到终点之间的片段加入右侧列表（快捷键 Enter）")
        b_add.clicked.connect(self.add_segment)
        tr.addWidget(b_add)
        left.addLayout(tr)

        # -- 右侧片段面板 --
        side = QFrame(objectName="Side")
        side.setFixedWidth(304)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 14, 14, 14)
        sv.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(QLabel("🎞 片段", objectName="H1"))
        head.addStretch(1)
        self.lbl_count = QLabel("0", objectName="Count")
        head.addWidget(self.lbl_count)
        sv.addLayout(head)

        self.listw = QListWidget(objectName="SegList")
        self.listw.setSpacing(3)
        self.listw.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.listw.itemDoubleClicked.connect(self._on_item_dclick)
        sv.addWidget(self.listw, 1)

        crop_row = QHBoxLayout()
        self.lbl_crop = QLabel("", objectName="SegTime")
        self.lbl_crop.setWordWrap(True)
        crop_row.addWidget(self.lbl_crop,1)
        self.btn_clear_crop = QPushButton("取消裁剪", objectName="Tiny")
        self.btn_clear_crop.clicked.connect(self.clear_crop)
        self.btn_clear_crop.hide()
        crop_row.addWidget(self.btn_clear_crop)
        sv.addLayout(crop_row)
        bright_row=QHBoxLayout()
        self.lbl_brightness=QLabel("导出亮度 0")
        bright_row.addWidget(self.lbl_brightness)
        bright_row.addStretch()
        reset_brightness=QPushButton("重置",objectName="Tiny")
        reset_brightness.clicked.connect(lambda:self.slider_brightness.setValue(0))
        bright_row.addWidget(reset_brightness)
        sv.addLayout(bright_row)
        self.slider_brightness=QSlider(Qt.Horizontal)
        self.slider_brightness.setRange(-50,50)
        self.slider_brightness.setValue(0)
        self.slider_brightness.setToolTip("0 保持原亮度，向左调暗，向右调亮；调整后重新编码导出。")
        self.slider_brightness.valueChanged.connect(self._brightness_changed)
        sv.addWidget(self.slider_brightness)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["⚡ 无损快剪", "🎯 逐帧精确"])
        self.cmb_mode.setToolTip("⚡ 无损:直接拷贝码流,秒出、零损;起点对齐关键帧,可能提前 1~2 秒\n🎯 精确:重编码,逐帧准,较慢")
        sv.addWidget(self.cmb_mode)
        self.chk_merge = QCheckBox("⧉ 合并输出")
        self.chk_merge.setToolTip("把所有片段拼成一个视频")
        sv.addWidget(self.chk_merge)

        orow = QHBoxLayout()
        self.lbl_out = QLabel("📁 视频同目录", objectName="Hint")
        self.lbl_out.setToolTip("导出位置")
        orow.addWidget(self.lbl_out, 1)
        b_dir = QPushButton("…", objectName="Tiny")
        b_dir.setToolTip("更改导出位置")
        b_dir.clicked.connect(self._pick_outdir)
        orow.addWidget(b_dir)
        sv.addLayout(orow)

        self.btn_export = QPushButton("🚀 导出", objectName="Primary")
        self.btn_export.setToolTip("导出全部片段 (Ctrl+E)")
        self.btn_export.clicked.connect(self.export_all)
        sv.addWidget(self.btn_export)
        outer.addWidget(side)

        # -- 状态栏 --
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setRange(0, 1000)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage(HINT)

    def _install_shortcuts(self):
        def sc(key, slot):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(slot)
        sc(Qt.Key_Space, self.toggle_play)
        sc(Qt.Key_I, self.mark_in)
        sc(Qt.Key_O, self.mark_out)
        sc(Qt.Key_Return, self.add_segment)
        sc(Qt.Key_Enter, self.add_segment)
        sc(Qt.Key_Left, lambda: self._jump(-5000))
        sc(Qt.Key_Right, lambda: self._jump(5000))
        sc(Qt.Key_Comma, lambda: self._jump(-40))
        sc(Qt.Key_Period, lambda: self._jump(40))
        sc(Qt.Key_Delete, self._delete_selected)
        sc(Qt.Key_Escape, self._clear_pending)
        sc("Ctrl+O", self.open_file)
        sc("Ctrl+E", self.export_all)

    def _apply_theme(self, key, save=True):
        if key not in THEMES:
            key = DEFAULT_THEME
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(build_qss(key))
        self.timeline.applyTheme(key)
        if save:
            self.settings.setValue("theme", key)
        idx = self.cmb_theme.findData(key)
        if idx >= 0 and self.cmb_theme.currentIndex() != idx:
            self.cmb_theme.blockSignals(True)
            self.cmb_theme.setCurrentIndex(idx)
            self.cmb_theme.blockSignals(False)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._dark_titlebar_done and os.name == "nt":
            self._dark_titlebar_done = True
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    int(self.winId()), 20, ctypes.byref(ctypes.c_int(1)), 4)
            except Exception:
                pass

    # ================= 打开 / 拖拽 =================
    def open_file(self):
        last = self.settings.value("last_dir", str(Path.home()))
        path, _ = QFileDialog.getOpenFileName(
            self, "选择视频", last,
            "视频文件 (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.ts *.m4v *.mpg *.mpeg);;所有文件 (*.*)")
        if path:
            self.load_path(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            p = Path(e.mimeData().urls()[0].toLocalFile())
            if p.suffix.lower() in VIDEO_EXTS:
                e.acceptProposedAction()

    def dropEvent(self, e):
        self.load_path(e.mimeData().urls()[0].toLocalFile())

    def load_path(self, path):
        path = str(path)
        if not Path(path).exists():
            return
        self.settings.setValue("last_dir", str(Path(path).parent))
        self._stop_thumbs()
        if self.crop_worker and self.crop_worker.isRunning():self.crop_worker.abort()
        self.clear_crop()
        self.slider_brightness.setValue(0)
        self.current = path
        self.segments = []
        self.pending_in = self.pending_out = None
        self.preview_end = None
        self._thumbs_started = False
        self.timeline.reset()
        self._refresh_segments()
        name = Path(path).name
        self.lbl_file.setText(name if len(name) <= 42 else name[:20] + "…" + name[-18:])
        self.lbl_file.setToolTip(path)
        self.stack.setCurrentIndex(1)
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()
        self.statusBar().showMessage(f"✔ {name} · {HINT}")

    # ================= 播放控制 =================
    def toggle_play(self):
        if not self.current:
            return
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _jump(self, delta_ms):
        if not self.current:
            return
        self.player.setPosition(max(0, min(self.player.duration(),
                                           self.player.position() + delta_ms)))

    def _on_position(self, pos):
        self.timeline.setPosition(pos)
        self.lbl_time.setText(f"{fmt_ms(pos)} / {fmt_ms(self.player.duration())}")
        if self.preview_end is not None and pos >= self.preview_end:
            self.preview_end = None
            self.player.pause()

    def _on_duration(self, dur):
        self.timeline.setDuration(dur)
        self.lbl_time.setText(f"{fmt_ms(self.player.position())} / {fmt_ms(dur)}")
        if dur > 0 and not self._thumbs_started and self.ffmpeg:
            self._thumbs_started = True
            self._start_thumbs(dur / 1000.0)

    def _on_state(self, state):
        self.btn_play.setText("⏸" if state == QMediaPlayer.PlayingState else "▶")

    def _on_error(self, err, msg):
        if err != QMediaPlayer.NoError:
            QMessageBox.warning(self, "播放失败", f"无法播放该视频:\n{msg or err}")

    # ================= 缩略图 =================
    def _start_thumbs(self, duration_s):
        d = tempfile.mkdtemp(prefix="clipcut_thumbs_")
        self.thumb_dirs.append(d)
        count = 28
        self.timeline.setThumbCount(count)
        self.thumb_worker = ThumbnailWorker(self.ffmpeg, self.current, duration_s, count, d, self)
        self.thumb_worker.thumbReady.connect(self._on_thumb)
        self.thumb_worker.start()

    def _on_thumb(self, i, path):
        pm = QPixmap(path)
        if not pm.isNull():
            self.timeline.addThumb(i, pm)

    def _stop_thumbs(self):
        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.requestInterruption()

    # ================= 打点 / 片段 =================
    def mark_in(self):
        if not self.current:
            return
        self.pending_in = self.player.position()
        self.timeline.setPending(self.pending_in, self.pending_out)
        self.statusBar().showMessage(f"⟦ {fmt_ms(self.pending_in, short=True)} · 按 O 设出点")

    def mark_out(self):
        if not self.current:
            return
        self.pending_out = self.player.position()
        self.timeline.setPending(self.pending_in, self.pending_out)
        if self.pending_in is None:
            self.statusBar().showMessage(f"{fmt_ms(self.pending_out, short=True)} ⟧ · 按 I 设入点")
        else:
            self.statusBar().showMessage(
                f"{fmt_ms(self.pending_in, short=True)} → {fmt_ms(self.pending_out, short=True)}"
                " · Enter 收藏")

    def _clear_pending(self):
        self.pending_in = self.pending_out = None
        self.timeline.setPending(None, None)
        self.statusBar().showMessage(HINT)

    def add_segment(self):
        if not self.current:
            return
        if self.pending_in is None and self.pending_out is None:
            self.statusBar().showMessage("先按 I / O 打点")
            return
        a = self.pending_in if self.pending_in is not None else 0
        b = self.pending_out if self.pending_out is not None else self.player.position()
        s, e = (a, b) if a <= b else (b, a)
        if e - s < 200:
            self.statusBar().showMessage("⚠ 片段太短(< 0.2s)")
            return
        self.segments.append((s, e))
        self.segments.sort()
        self.pending_in = self.pending_out = None
        self.timeline.setPending(None, None)
        self.timeline.setSegments(self.segments)
        self._refresh_segments()
        self.statusBar().showMessage(
            f"★ {fmt_ms(s, short=True)} → {fmt_ms(e, short=True)} · 共 {len(self.segments)} 段")

    def _refresh_segments(self):
        self.listw.clear()
        for n, (s, e) in enumerate(self.segments, 1):
            item = QListWidgetItem(self.listw)
            item.setSizeHint(QSize(0, 62))
            card = QFrame(objectName="SegCard")
            h = QHBoxLayout(card)
            h.setContentsMargins(10, 6, 8, 6)
            h.setSpacing(6)
            v = QVBoxLayout()
            v.setSpacing(2)
            v.addWidget(QLabel(f"{n:02d} · {(e - s) / 1000:.1f}s", objectName="SegTitle"))
            v.addWidget(QLabel(f"{fmt_ms(s, short=True)} → {fmt_ms(e, short=True)}",
                               objectName="SegTime"))
            h.addLayout(v, 1)
            bp = QPushButton("▶", objectName="Tiny")
            bp.setToolTip("试看")
            bp.clicked.connect(lambda _=False, i=n - 1: self._preview_segment(i))
            h.addWidget(bp)
            bd = QPushButton("✕", objectName="Tiny")
            bd.setProperty("id", "Del")
            bd.setObjectName("Del")
            bd.setToolTip("删除 (Del)")
            bd.clicked.connect(lambda _=False, i=n - 1: self._delete_segment(i))
            h.addWidget(bd)
            self.listw.setItemWidget(item, card)
        self.lbl_count.setText(str(len(self.segments)))
        for b in self.listw.findChildren(QPushButton):
            b.setFocusPolicy(Qt.NoFocus)

    def _on_item_dclick(self, item):
        i = self.listw.row(item)
        if 0 <= i < len(self.segments):
            self.player.setPosition(self.segments[i][0])

    def _preview_segment(self, i):
        if 0 <= i < len(self.segments):
            s, e = self.segments[i]
            self.preview_end = e
            self.player.setPosition(s)
            self.player.play()

    def _delete_segment(self, i):
        if 0 <= i < len(self.segments):
            s, e = self.segments.pop(i)
            self.timeline.setSegments(self.segments)
            self._refresh_segments()
            self.statusBar().showMessage(
                f"✕ {fmt_ms(s, short=True)} → {fmt_ms(e, short=True)}")

    def _delete_selected(self):
        self._delete_segment(self.listw.currentRow())

    # ================= 导出 =================
    def edit_crop(self):
        if not self.current:
            self.statusBar().showMessage("请先打开视频，再框选画面。")
            return
        if not self.ffmpeg:
            self._warn_no_ffmpeg();return
        if self.export_worker and self.export_worker.isRunning():return
        if self.crop_worker and self.crop_worker.isRunning():return
        self.player.pause()
        self.btn_crop.setEnabled(False)
        self.btn_crop.setText("读取画面…")
        self.crop_worker=FrameWorker(self.ffmpeg,self.current,max(0,min(self.player.position(),self.player.duration()-100)),self)
        self.crop_worker.result.connect(self._crop_frame)
        self.crop_worker.finished.connect(self._crop_finished)
        self.crop_worker.start()

    def _crop_finished(self):
        self.btn_crop.setText("裁剪画面");self.btn_crop.setEnabled(True)

    def _crop_frame(self,path,data,error):
        if path!=self.current:return
        if error:
            QMessageBox.warning(self,"无法读取画面",error);return
        image=QImage.fromData(data)
        if image.isNull():
            QMessageBox.warning(self,"无法读取画面","请稍微后退后重试。");return
        dialog=CropDialog(image,self.crop_rect,self)
        if dialog.exec()!=CropDialog.Accepted:return
        self.crop_rect=dialog.crop()
        self.video.set_crop(self.crop_rect,(image.width(),image.height()))
        x,y,w,h=self.crop_rect
        self.lbl_crop.setText(f"裁剪 {w} × {h} · 重新编码")
        self.lbl_crop.setToolTip("统一应用于所有片段；未添加片段时导出整段视频。")
        self.btn_clear_crop.show()
        self._sync_export_mode()
        self.statusBar().showMessage(f"已设置画面裁剪 {w} × {h}；未添加片段时将导出整段视频。")

    def clear_crop(self):
        self.crop_rect=None
        self.video.set_crop()
        self.lbl_crop.clear();self.btn_clear_crop.hide();self._sync_export_mode()

    def _sync_export_mode(self):
        active=self.crop_rect is not None or self.slider_brightness.value()!=0
        if active and not self._processing_active:self._crop_previous_mode=self.cmb_mode.currentIndex()
        self._processing_active=active
        self.cmb_mode.setCurrentIndex(1 if active else self._crop_previous_mode)
        self.cmb_mode.setEnabled(not active)

    def _brightness_changed(self,value):
        self.lbl_brightness.setText(f"导出亮度 {value:+d}" if value else "导出亮度 0")
        self.video.set_brightness(value/100)
        self._sync_export_mode()

    def _pick_outdir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹",
                                             self.custom_outdir or str(Path.home()))
        if d:
            self.custom_outdir = d
            self.lbl_out.setText(f"📁 {d}")
            self.lbl_out.setToolTip(d)

    def _default_outdir(self) -> Path:
        src = Path(self.current)
        return src.parent / f"{src.stem}_精彩片段"

    def export_all(self):
        if not self.current or (not self.segments and not self.crop_rect and not self.slider_brightness.value()):
            QMessageBox.information(self, "没有片段", "先按 I / O 打点,Enter 收藏。")
            return
        if not self.ffmpeg:
            self._warn_no_ffmpeg()
            return
        if self.export_worker and self.export_worker.isRunning():
            return
        outdir = Path(self.custom_outdir) if self.custom_outdir else self._default_outdir()
        precise = self.cmb_mode.currentIndex() == 1
        merge = self.chk_merge.isChecked()
        segments=self.segments or [(0,self.player.duration())]
        if any(e<=s for s,e in segments):
            QMessageBox.warning(self,"无法导出","视频时长尚未就绪，请稍后重试。");return
        self.export_worker = ExportWorker(self.ffmpeg, self.current, segments,
                                          outdir, precise=precise, merge=merge, parent=self, crop=self.crop_rect,
                                          brightness=self.slider_brightness.value()/100)
        self.export_worker.progress.connect(self._on_export_progress)
        self.export_worker.done.connect(self._on_export_done)
        self.btn_export.setEnabled(False)
        self.btn_export.setText("⏳ 导出中")
        self.progress.setValue(0)
        self.progress.show()
        self.export_worker.start()

    def _on_export_progress(self, frac, text):
        self.progress.setValue(int(frac * 1000))
        self.statusBar().showMessage(text)

    def _on_export_done(self, ok, msg, outdir):
        self.btn_export.setEnabled(True)
        self.btn_export.setText("🚀 导出")
        self.progress.hide()
        if ok:
            self.statusBar().showMessage(f"✅ {msg}")
            box = QMessageBox(self)
            box.setWindowTitle("完成")
            box.setText(f"{msg}\n\n📁 {outdir}")
            open_btn = box.addButton("📂 打开", QMessageBox.AcceptRole)
            box.addButton("好", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is open_btn:
                try:
                    os.startfile(outdir)
                except Exception:
                    pass
        else:
            self.statusBar().showMessage("❌ 导出失败")
            QMessageBox.warning(self, "导出失败", msg)

    def _warn_no_ffmpeg(self):
        QMessageBox.warning(
            self, "缺少 ffmpeg",
            "未找到 ffmpeg,无法导出和生成缩略图。\n\n"
            "把 ffmpeg.exe 放到程序同目录,或装入系统 PATH。\n"
            "下载:ffmpeg.org")

    # ================= 收尾 =================
    def closeEvent(self, e):
        if self.crop_worker and self.crop_worker.isRunning():
            self.crop_worker.abort()
            if not self.crop_worker.wait(1500):
                e.ignore();QTimer.singleShot(200,self.close);return
        if self.export_worker and self.export_worker.isRunning():
            r = QMessageBox.question(self, "正在导出", "导出未完成,确定退出?")
            if r != QMessageBox.Yes:
                e.ignore()
                return
            self.export_worker.abort()
            self.export_worker.wait(3000)
        if self.thumb_worker and self.thumb_worker.isRunning():
            self.thumb_worker.requestInterruption()
            self.thumb_worker.wait(2000)
        self.player.stop()
        for d in self.thumb_dirs:
            shutil.rmtree(d, ignore_errors=True)
        super().closeEvent(e)
