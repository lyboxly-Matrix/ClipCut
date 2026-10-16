# -*- coding: utf-8 -*-
"""自检模式(CLIPCUT_SELFTEST=ui|full):真实窗口抓图 + 全链路加载/打点/导出验证。
结果写入 CLIPCUT_SELFTEST_DIR(截图 + report.json),退出码 0=通过。"""
import json
import os
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from workers import ExportWorker, probe_duration

SEGMENTS = [(5000, 12000), (20000, 26000)]      # 测试片段(毫秒)


class SelfTest(QObject):
    def __init__(self, win, mode):
        super().__init__(win)
        self.win = win
        self.mode = mode
        self.outdir = Path(os.environ.get("CLIPCUT_SELFTEST_DIR", tempfile.gettempdir()))
        self.outdir.mkdir(parents=True, exist_ok=True)
        self.report = {"mode": mode, "steps": [], "ok": False}
        self.t0 = time.time()
        QTimer.singleShot(45000, lambda: self.finish(2, "timeout"))
        QTimer.singleShot(1000, self.step_empty)

    def log(self, msg):
        self.report["steps"].append(f"[{time.time() - self.t0:5.1f}s] {msg}")

    def snap(self, name):
        pm = self.win.grab()
        path = self.outdir / f"{name}.png"
        pm.save(str(path))
        img = pm.toImage()
        lit = 0
        for yy in range(0, img.height(), 16):
            for xx in range(0, img.width(), 16):
                c = img.pixelColor(xx, yy)
                if c.red() > 45 or c.green() > 45 or c.blue() > 45:
                    lit += 1
        self.log(f"截图 {name}.png,亮像素采样 {lit}")
        return lit

    def step_empty(self):
        lit = self.snap("st_empty")
        if lit < 10:
            return self.finish(2, "空态界面几乎全黑,渲染异常")
        if self.mode == "ui":
            return self.finish(0, "UI 渲染正常")
        sample = os.environ.get("CLIPCUT_SAMPLE")
        if not sample or not Path(sample).exists():
            return self.finish(2, "缺少 CLIPCUT_SAMPLE 测试视频")
        self.log(f"加载样片 {sample}")
        self.win.load_path(sample)
        self.polls = 0
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_loaded)
        self.poll_timer.start(250)

    def poll_loaded(self):
        self.polls += 1
        dur = self.win.player.duration()
        if dur > 0:
            self.poll_timer.stop()
            self.report["duration_ms"] = dur
            self.log(f"视频加载成功,时长 {dur}ms")
            self.win.player.setPosition(8000)
            QTimer.singleShot(1200, self.step_crop if self.mode in ('crop','cropbright','livecrop','livebright') else self.step_marks)
        elif self.polls > 48:
            self.poll_timer.stop()
            self.finish(2, "视频加载超时(duration 一直为 0)")

    def step_crop(self):
        from crop import FrameWorker, CropDialog
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication, QComboBox
        self.win.player.pause()
        if self.mode in ('cropbright','livebright'):self.win.slider_brightness.setValue(20)
        def accept_crop():
            dialog=QApplication.activeModalWidget()
            if not isinstance(dialog,CropDialog):return self.finish(2,'裁剪对话框未打开')
            dialog.findChild(QComboBox).setCurrentIndex(2)
            c=dialog.canvas;r=c.image_rect()
            a=QPoint(int(r.left()+r.width()*.2),int(r.top()+r.height()*.1))
            b=QPoint(int(r.left()+r.width()*.7),int(r.top()+r.height()*.9))
            QTest.mousePress(c,Qt.LeftButton,pos=a);QTest.mouseMove(c,b);QTest.mouseRelease(c,Qt.LeftButton,pos=b)
            dialog.grab().save(str(self.outdir/'crop-dialog.png'))
            dialog.accept()
        def on_frame(path,data,error):
            if error:return self.finish(2,error)
            QTimer.singleShot(200,accept_crop)
            self.win._crop_frame(path,data,error)
            crop=self.win.crop_rect
            if not crop or crop[2]*16!=crop[3]*9:return self.finish(2,'竖屏裁剪比例不正确')
            self.report['crop']=crop
            if self.mode in ('livecrop','livebright'):
                if self.mode=='livebright' and not self.win.video.brightness.isEnabled():return self.finish(2,'主画面亮度未生效')
                if self.win.video.crop!=crop:return self.finish(2,'主播放画面未应用裁剪')
                self.win.player.play()
                QTimer.singleShot(400,self.step_live_seek)
                return
            self.step_marks()
        self.capture=FrameWorker(self.win.ffmpeg,self.win.current,8000,self)
        self.capture.result.connect(on_frame);self.capture.start()

    def step_live_seek(self):
        self.win.player.setPosition(15000)
        QTimer.singleShot(400,self.step_live_done)

    def step_live_done(self):
        self.win.player.pause()
        self.snap('live-cropped')
        if self.mode=='livebright':
            self.win.slider_brightness.setValue(0)
            if self.win.video.brightness.isEnabled():return self.finish(2,'亮度重置失败')
        if self.win.video.crop!=tuple(self.report['crop']):return self.finish(2,'播放或跳转后丢失裁剪')
        self.win.clear_crop()
        if self.win.video.crop is not None:return self.finish(2,'取消裁剪未恢复全画面')
        self.snap('live-restored')
        self.finish(0,'实时裁剪播放、进度跳转及恢复全画面通过')

    def step_marks(self):
        w = self.win
        w.player.pause()
        # 模拟打点:I → O → Enter,走真实代码路径
        for s, e in SEGMENTS:
            w.player.setPosition(s)
            w.pending_in = s
            w.pending_out = e
            w.add_segment()
        self.log(f"已收藏 {len(w.segments)} 段:{w.segments}")
        if len(w.segments) != len(SEGMENTS):
            return self.finish(2, "片段收藏数量不对")
        QTimer.singleShot(5000, self.step_export)   # 等缩略图基本抽完再截图

    def step_export(self):
        tw = self.win.thumb_worker
        if tw:
            bad = {k: v for k, v in tw.results.items() if v != "ok"}
            self.report["thumbs"] = {"loaded": len(self.win.timeline._thumbs),
                                     "results": len(tw.results), "bad": bad}
            self.log(f"缩略图 {len(self.win.timeline._thumbs)}/{tw.count},失败 {bad}")
        self.snap("st_loaded")
        from theme import THEMES
        for key in THEMES:
            self.win._apply_theme(key, save=False)
            self.snap(f"st_theme_{key}")
        clips = self.outdir / "clips"
        self.worker = ExportWorker(self.win.ffmpeg, self.win.current,
                                   self.win.segments, clips,
                                   precise=False, merge=False, parent=self,
                                   crop=self.win.crop_rect if self.mode in ('crop','cropbright') else None,
                                   brightness=self.win.slider_brightness.value()/100)
        self.worker.done.connect(self.on_export_done)
        self.log("开始裁剪导出" if self.mode in ('crop','cropbright') else "开始无损导出")
        self.worker.start()

    def on_export_done(self, ok, msg, outdir):
        self.log(f"导出结果 ok={ok} msg={msg}")
        if not ok:
            return self.finish(2, f"导出失败:{msg}")
        files = sorted(Path(outdir).glob("*.*"))
        self.report["outputs"] = []
        for f, (s, e) in zip(files, SEGMENTS):
            if self.mode in ('crop','cropbright'):
                from workers import find_tool,run_hidden
                r=run_hidden([find_tool('ffprobe'),'-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(f)])
                video=json.loads(r.stdout)['streams'][0]
                if (video['width'],video['height'])!=tuple(self.report['crop'][2:]):return self.finish(2,'导出尺寸与裁剪框不符')
            want = (e - s) / 1000.0
            got = probe_duration(f)
            self.report["outputs"].append({"file": f.name, "want_s": want, "got_s": round(got, 2)})
            # copy 模式从关键帧切,允许 -0.5 ~ +2.5 秒偏差
            if not (want - 0.5 <= got <= want + 2.5):
                return self.finish(2, f"{f.name} 时长异常:期望≈{want}s 实际 {got:.2f}s")
        if len(files) < len(SEGMENTS):
            return self.finish(2, f"导出文件数不足:{len(files)}/{len(SEGMENTS)}")
        self.snap("st_done")
        self.finish(0, "全链路自检通过")

    def finish(self, code, msg):
        self.report["ok"] = code == 0
        self.report["result"] = msg
        (self.outdir / "report.json").write_text(
            json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log(msg)
        self.win.close()          # 走 closeEvent,等待缩略图/导出线程收尾,避免退出崩溃
        QTimer.singleShot(0, lambda: QApplication.exit(code))
