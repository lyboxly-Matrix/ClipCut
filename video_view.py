"""GPU-backed playback viewport cropped in displayed-frame coordinates."""
from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QImage, QTransform
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QFrame, QGraphicsRectItem, QGraphicsItem, QGraphicsEffect
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtMultimedia import QVideoFrameFormat

class BrightnessEffect(QGraphicsEffect):
    """Apply the video luma offset to screen-sized pixels; keep bars black."""
    def __init__(self,parent=None):
        super().__init__(parent);self.value=0;self.full_range=False;self.table=bytes(range(256))
        self.setEnabled(False)
    def set_value(self,value,full_range=None):
        if full_range is not None:self.full_range=full_range
        self.value=value
        delta=round(value*256*(1 if self.full_range else 255/219))
        self.table=bytes(max(0,min(255,i+delta)) for i in range(256))
        self.setEnabled(value!=0);self.update()
    def draw(self,painter):
        offset=QPoint()
        pixmap=self.sourcePixmap(Qt.DeviceCoordinates,offset,QGraphicsEffect.NoPad)
        if pixmap.isNull():return
        image=pixmap.toImage().convertToFormat(QImage.Format_RGB888)
        data=bytes(image.constBits()).translate(self.table)
        adjusted=QImage(data,image.width(),image.height(),image.bytesPerLine(),QImage.Format_RGB888)
        adjusted.setDevicePixelRatio(image.devicePixelRatio())
        painter.save();painter.setWorldTransform(QTransform());painter.drawImage(offset,adjusted);painter.restore()

class VideoView(QGraphicsView):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.clip=QGraphicsRectItem()
        self.clip.setPen(QPen(Qt.NoPen))
        self.clip.setFlag(QGraphicsItem.ItemClipsChildrenToShape,True)
        self.scene().addItem(self.clip)
        self.item=QGraphicsVideoItem(self.clip)
        self.brightness=BrightnessEffect(self)
        self.item.setGraphicsEffect(self.brightness)
        self.item.setAspectRatioMode(Qt.IgnoreAspectRatio)
        self.item.nativeSizeChanged.connect(self._native_size)
        self.item.videoSink().videoSizeChanged.connect(self._display_size)
        self.item.videoSink().videoFrameChanged.connect(self._frame_range)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor('black')))
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.crop=None;self.source_size=None
    def videoSink(self):return self.item.videoSink()
    def set_brightness(self,value):
        self.brightness.set_value(value)
        self.viewport().update()
    def _frame_range(self,frame):
        full=frame.surfaceFormat().colorRange()==QVideoFrameFormat.ColorRange.ColorRange_Full
        if full!=self.brightness.full_range:self.brightness.set_value(self.brightness.value,full)
    def _native_size(self,size):
        displayed=self.item.videoSink().videoSize()
        if not displayed.isEmpty():size=displayed
        if size.isEmpty():return
        self.item.setSize(size)
        self._fit()
    def _display_size(self):
        self._native_size(self.item.videoSink().videoSize())
    def set_crop(self,crop=None,source_size=None):
        self.crop=crop
        self.source_size=source_size
        self._fit()
    def _fit(self):
        rect=self.item.boundingRect()
        if rect.isEmpty():return
        if self.crop and self.source_size:
            x,y,w,h=self.crop;sw,sh=self.source_size
            rect=QRectF(x*rect.width()/sw,y*rect.height()/sh,w*rect.width()/sw,h*rect.height()/sh)
        self.clip.setRect(rect)
        self.setSceneRect(rect)
        self.fitInView(rect,Qt.KeepAspectRatio)
        self.viewport().update()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._fit()
