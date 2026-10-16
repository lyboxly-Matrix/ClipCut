# -*- coding: utf-8 -*-
"""ffmpeg 相关:工具定位、时长探测、缩略图线程、导出线程。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

from PySide6.QtCore import QThread, Signal

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def find_tool(name: str):
    """优先 EXE 同目录,其次 PATH。返回绝对路径或 None。"""
    exe = f"{name}.exe" if os.name == "nt" else name
    local = app_dir() / exe
    if local.exists():
        return str(local)
    return shutil.which(name)


def run_hidden(args, timeout=None):
    return subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, creationflags=CREATE_NO_WINDOW)


def probe_duration(path) -> float:
    """用 ffprobe 拿视频时长(秒),失败返回 0。"""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        return 0.0
    try:
        r = run_hidden([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "json", str(path)], timeout=30)
        return float(json.loads(r.stdout)["format"]["duration"])
    except Exception:
        return 0.0


def fmt_ms(ms: int, short=False) -> str:
    """毫秒 → 00:12:03.5;short 模式无小时时省略小时位。"""
    ms = max(0, int(ms))
    h, rest = divmod(ms, 3600_000)
    m, rest = divmod(rest, 60_000)
    s = rest / 1000.0
    if short and h == 0:
        return f"{m:02d}:{s:04.1f}"
    return f"{h:02d}:{m:02d}:{s:04.1f}"


def _tag(ms: int) -> str:
    """毫秒 → 文件名友好的时间标记,如 05m12s / 1h02m03s。"""
    sec = int(ms / 1000)
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m:02d}m{s:02d}s"


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 999):
        cand = path.with_stem(f"{path.stem}_{i}")
        if not cand.exists():
            return cand
    return path


class ThumbnailWorker(QThread):
    """按时间点逐张抽帧(关键帧快速 seek),边抽边回传,时间轴逐渐填满。"""
    thumbReady = Signal(int, str)          # index, jpg 路径

    def __init__(self, ffmpeg, src, duration_s, count, outdir, parent=None):
        super().__init__(parent)
        self.ffmpeg, self.src = ffmpeg, str(src)
        self.duration_s, self.count, self.outdir = duration_s, count, Path(outdir)
        self.results = {}              # index -> "ok" / 失败原因(诊断用)

    def run(self):
        if not self.ffmpeg or self.duration_s <= 0:
            return
        todo = list(range(self.count))
        for round_no in (1, 2):        # 失败的索引整体重试一轮
            failed = []
            for i in todo:
                if self.isInterruptionRequested():
                    return
                if not self._grab(i):
                    failed.append(i)
            todo = failed
            if not todo:
                break

    def _grab(self, i) -> bool:
        t = (i + 0.5) * self.duration_s / self.count
        out = self.outdir / f"thumb_{i:03d}.jpg"
        try:
            r = run_hidden([self.ffmpeg, "-hide_banner", "-ss", f"{t:.2f}",
                            "-i", self.src, "-frames:v", "1",
                            "-vf", "scale=176:-2", "-q:v", "4", "-y", str(out)],
                           timeout=20)
            if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
                self.results[i] = "ok"
                self.thumbReady.emit(i, str(out))
                return True
            self.results[i] = f"rc={r.returncode} {r.stderr[-160:]}"
        except Exception as ex:
            self.results[i] = f"exc={ex}"
        return False


class ExportWorker(QThread):
    """逐段调 ffmpeg 剪切;可选合并为一个文件。copy 模式无损秒剪。"""
    progress = Signal(float, str)          # 0~1, 文字
    done = Signal(bool, str, str)          # ok, message, outdir

    def __init__(self, ffmpeg, src, segments, outdir, precise=False, merge=False, parent=None, crop=None, brightness=0):
        super().__init__(parent)
        self.ffmpeg, self.src = ffmpeg, Path(src)
        self.segments, self.outdir = list(segments), Path(outdir)
        self.crop = tuple(crop) if crop else None
        self.brightness = float(brightness)
        self.precise, self.merge = precise or self.crop is not None or self.brightness != 0, merge
        self._proc = None
        self._aborted = False

    def abort(self):
        self._aborted = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def run(self):
        workdir = None
        try:
            self.outdir.mkdir(parents=True, exist_ok=True)
            ext = ".mp4" if self.precise else (self.src.suffix or ".mp4")
            workdir = Path(tempfile.mkdtemp(prefix="clipcut_")) if self.merge else None
            total = max(0.1, sum((e - s) for s, e in self.segments) / 1000.0)
            done_s, parts = 0.0, []

            for n, (s_ms, e_ms) in enumerate(self.segments, 1):
                if self._aborted:
                    raise RuntimeError("已取消导出")
                start, dur = s_ms / 1000.0, (e_ms - s_ms) / 1000.0
                name = f"{self.src.stem}_片段{n:02d}_{_tag(s_ms)}-{_tag(e_ms)}{ext}"
                out = _unique((workdir or self.outdir) / name)
                cmd = [self.ffmpeg, "-hide_banner", "-y",
                       "-ss", f"{start:.3f}", "-i", str(self.src), "-t", f"{dur:.3f}"]
                filters=[]
                if self.crop:
                    x,y,w,h=self.crop
                    if min(x,y)<0 or min(w,h)<2 or any(v%2 for v in self.crop):
                        raise ValueError('裁剪区域无效，请重新框选。')
                    from crop import NORMALIZE
                    filters += [NORMALIZE,f"crop={w}:{h}:{x}:{y}"]
                if self.brightness:
                    if not -.5<=self.brightness<=.5:raise ValueError('亮度超出可调范围。')
                    filters.append(f"eq=brightness={self.brightness:.3f}")
                if filters:
                    cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-vf", ','.join(filters)]
                if self.precise:
                    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                            "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
                else:
                    cmd += ["-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
                            "-avoid_negative_ts", "make_zero"]
                cmd += ["-nostats", "-progress", "pipe:1", str(out)]
                self._run_ffmpeg(cmd, dur, done_s, total,
                                 f"⏳ 导出 {n}/{len(self.segments)}")
                parts.append(out)
                done_s += dur

            if self.merge and parts:
                self.progress.emit(0.98, "⏳ 合并中")
                lst = workdir / "list.txt"
                lines = []
                for p in parts:
                    q = p.as_posix().replace("'", "'\\''")
                    lines.append(f"file '{q}'")
                lst.write_text("\n".join(lines), encoding="utf-8")
                mout = _unique(self.outdir / f"{self.src.stem}_精彩合集{ext}")
                r = run_hidden([self.ffmpeg, "-hide_banner", "-y", "-f", "concat",
                                "-safe", "0", "-i", str(lst), "-c", "copy", str(mout)])
                if r.returncode != 0:
                    raise RuntimeError(f"合并失败:{r.stderr[-400:]}")
                msg = f"已导出合集 {mout.name}"
            else:
                msg = f"已导出 {len(parts)} 段"
            self.progress.emit(1.0, "✅ 完成")
            self.done.emit(True, msg, str(self.outdir))
        except Exception as ex:
            self.done.emit(False, str(ex), str(self.outdir))
        finally:
            if workdir:
                shutil.rmtree(workdir, ignore_errors=True)

    def _run_ffmpeg(self, cmd, seg_dur, done_s, total, label):
        tail = deque(maxlen=30)
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            creationflags=CREATE_NO_WINDOW)
        for line in self._proc.stdout:
            line = line.strip()
            if line:
                tail.append(line)
            if line.startswith("out_time_us="):
                try:
                    cur = int(line.split("=", 1)[1]) / 1e6
                    self.progress.emit(min(0.99, (done_s + min(cur, seg_dur)) / total), label)
                except ValueError:
                    pass
        self._proc.wait()
        if self._aborted:
            raise RuntimeError("已取消导出")
        if self._proc.returncode != 0:
            raise RuntimeError("ffmpeg 失败:" + " | ".join(list(tail)[-5:]))
