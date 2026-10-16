# ClipCut

Windows 视频剪辑工具，使用 Python 3.11、PySide6 和 FFmpeg。

## 功能

- 手动设置起点、终点，添加多个片段，分别导出或合并。
- 无损快剪和重新编码的逐帧精确导出。
- 鼠标框选画面、移动选区、拖动四角调整大小。
- 锁定 16:9、9:16、1:1、4:3、4:5 或原画面比例；自由框选提供常用比例建议和输出尺寸。
- 裁剪实时应用到主播放画面，播放、暂停和拖动进度时均生效。
- 导出亮度滑动条（-50～+50），主画面即时预览，可与裁剪叠加；0 保持原亮度。

## 使用 Windows 版本

在本仓库 Releases 下载 Windows ZIP，完整解压后运行 `ClipCut.exe`。请保留旁边的 `文件` 文件夹。

需要在系统 PATH 中安装 FFmpeg 和 FFprobe，或将这两个程序放在 EXE 同目录。FFmpeg 下载与安装说明见 <https://ffmpeg.org/download.html>。

1. 打开或拖入视频。
2. 点击「设为起点」「设为终点」「添加片段」，再点击「导出」。
3. 如需裁剪，点击「裁剪画面」并框选，选择比例后应用。
4. 如需调亮或调暗，拖动右侧「导出亮度」滑动条；点击「重置」恢复原亮度。

有已添加的片段时，裁剪与亮度统一应用于这些片段；没有片段时，设置裁剪或亮度后可直接导出整段视频。打开另一视频时清除裁剪并恢复原亮度。

裁剪或非零亮度需要重新编码，输出 H.264 / AAC MP4。裁剪保持选区像素尺寸，不拉伸、不放大；坐标和尺寸对齐到偶数像素。无损快剪的起点可能对齐到较早的关键帧。

## 快捷键

| 快捷键 | 操作 |
| --- | --- |
| Space | 播放 / 暂停 |
| I / O | 设置起点 / 终点 |
| Enter | 添加片段 |
| ← / → | 后退 / 前进 5 秒 |
| , / . | 逐帧移动 |
| Delete | 删除选中的片段 |
| Esc | 清除时间打点 |
| Ctrl+O / Ctrl+E | 打开 / 导出 |

## 源码运行与构建

安装 Python 3.11，在仓库目录执行：

```powershell
python -m pip install -r requirements.txt
python main.py
```

Windows 打包可运行 `build.ps1`，脚本使用独立 `.buildenv` 环境，成功后生成 `dist\ClipCut\ClipCut.exe` 和 `dist\ClipCut\文件`。两者需一起分发。

源码入口为 `main.py`；界面在 `app.py`，裁剪选择在 `crop.py`，实时播放效果在 `video_view.py`，导出在 `workers.py`。

第三方依赖说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。不包含自动开球识别功能、用户视频或导出结果。
