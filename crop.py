"""Frame selection in displayed, square-pixel video coordinates."""
import math
import subprocess
import threading
from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox
from workers import CREATE_NO_WINDOW

NORMALIZE = 'scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1'
RATIOS = [('自由框选', None), ('16:9 · 横屏', (16,9)), ('9:16 · 竖屏', (9,16)),
          ('1:1 · 方形', (1,1)), ('4:3 · 横屏', (4,3)), ('4:5 · 竖屏', (4,5))]

def pixel_rect(rect, width, height, ratio=None):
    r=rect.normalized().intersected(QRectF(0,0,width,height))
    if ratio:
        a,b=ratio; g=math.gcd(a,b); a,b=a//g,b//g
        step=2 if a%2 or b%2 else 1
        k=int(min(r.width()/a,r.height()/b))//step*step
        w,h=a*k,b*k
    else:
        w,h=int(r.width())//2*2,int(r.height())//2*2
    if w<2 or h<2:return None
    x=min(max(0,int(r.x())//2*2),(width-w)//2*2)
    y=min(max(0,int(r.y())//2*2),(height-h)//2*2)
    return x,y,w,h

class FrameWorker(QThread):
    result=Signal(str,bytes,str)
    def __init__(self,ffmpeg,path,position,parent=None,brightness=0):
        super().__init__(parent); self.ffmpeg=ffmpeg; self.path=path; self.position=position
        self.proc=None; self.lock=threading.Lock();self.brightness=brightness
    def abort(self):
        self.requestInterruption()
        with self.lock:
            if self.proc and self.proc.poll() is None:self.proc.kill()
    def run(self):
        try:
            with self.lock:
                if self.isInterruptionRequested():return
                self.proc=subprocess.Popen([self.ffmpeg,'-hide_banner','-loglevel','error','-ss',str(self.position/1000),
                    '-i',self.path,'-map','0:v:0','-frames:v','1','-vf',NORMALIZE+(f',eq=brightness={self.brightness:.3f}' if self.brightness else ''),'-f','image2pipe','-vcodec','png','pipe:1'],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=CREATE_NO_WINDOW)
            data,err=self.proc.communicate(timeout=30)
            if self.isInterruptionRequested():return
            if self.proc.returncode or not data:raise RuntimeError(err.decode('utf-8','replace')[-400:] or '当前位置没有可用画面，请稍微后退再试。')
            self.result.emit(self.path,data,'')
        except Exception as ex:
            with self.lock:
                if self.proc and self.proc.poll() is None:self.proc.kill();self.proc.communicate()
            if not self.isInterruptionRequested():self.result.emit(self.path,b'',str(ex))

class CropCanvas(QWidget):
    changed=Signal()
    def __init__(self,image,crop=None,parent=None):
        super().__init__(parent); self.image=image; self.ratio=None
        self.selection=QRectF(*crop) if crop else QRectF()
        self.drag=None; self.setMinimumSize(560,320);self.setMouseTracking(True)
    def image_rect(self):
        w,h=self.image.width(),self.image.height();s=min(self.width()/w,self.height()/h)
        return QRectF((self.width()-w*s)/2,(self.height()-h*s)/2,w*s,h*s)
    def point(self,p):
        r=self.image_rect();return QPointF(max(0,min(self.image.width(),(p.x()-r.x())*self.image.width()/r.width())),
            max(0,min(self.image.height(),(p.y()-r.y())*self.image.height()/r.height())))
    def display_rect(self):
        r=self.image_rect();s=r.width()/self.image.width();v=self.selection
        return QRectF(r.x()+v.x()*s,r.y()+v.y()*s,v.width()*s,v.height()*s)
    def set_ratio(self,ratio):
        self.ratio=ratio
        if ratio:
            r=self.selection; a,b=ratio; w=min(r.width(),r.height()*a/b);h=w*b/a
            self.selection=QRectF(r.center().x()-w/2,r.center().y()-h/2,w,h)
        self.commit()
    def commit(self):
        crop=pixel_rect(self.selection,self.image.width(),self.image.height(),self.ratio)
        if crop:self.selection=QRectF(*crop)
        self.update();self.changed.emit()
    def mousePressEvent(self,e):
        if e.button()!=Qt.LeftButton or not self.image_rect().contains(e.position()):return
        p=self.point(e.position());r=self.selection;d=self.display_rect()
        corners=[(d.topLeft(),r.bottomRight()),(d.topRight(),r.bottomLeft()),(d.bottomLeft(),r.topRight()),(d.bottomRight(),r.topLeft())]
        for screen,opposite in corners:
            if (screen-e.position()).manhattanLength()<16:
                self.drag=('size',opposite);return
        if r.contains(p):self.drag=('move',p,QRectF(r))
        else:self.drag=('size',p);self.selection=QRectF(p,p)
    def mouseMoveEvent(self,e):
        if not self.drag:return
        p=self.point(e.position());mode=self.drag[0]
        if mode=='move':
            r=QRectF(self.drag[2]);delta=p-self.drag[1]
            r.moveTo(max(0,min(self.image.width()-r.width(),r.x()+delta.x())),max(0,min(self.image.height()-r.height(),r.y()+delta.y())))
        else:
            anchor=self.drag[1];dx=p.x()-anchor.x();dy=p.y()-anchor.y()
            if self.ratio:
                a,b=self.ratio;w=min(abs(dx),abs(dy)*a/b);h=w*b/a
                p=QPointF(anchor.x()+math.copysign(w,dx),anchor.y()+math.copysign(h,dy))
            r=QRectF(anchor,p).normalized()
        self.selection=r;self.update();self.changed.emit()
    def mouseReleaseEvent(self,e):
        if self.drag:self.drag=None;self.commit()
    def paintEvent(self,e):
        p=QPainter(self);p.fillRect(self.rect(),QColor('#12151b'));r=self.image_rect();p.drawImage(r,self.image)
        d=self.display_rect();shade=QColor(0,0,0,150)
        for area in [QRectF(r.left(),r.top(),r.width(),max(0,d.top()-r.top())),QRectF(r.left(),d.bottom(),r.width(),max(0,r.bottom()-d.bottom())),
                     QRectF(r.left(),d.top(),max(0,d.left()-r.left()),d.height()),QRectF(d.right(),d.top(),max(0,r.right()-d.right()),d.height())]:p.fillRect(area,shade)
        p.setPen(QPen(QColor('#e9bd69'),2));p.drawRect(d)
        p.setPen(QPen(QColor(255,255,255,85),1))
        for f in (1/3,2/3):
            p.drawLine(QPointF(d.left()+d.width()*f,d.top()),QPointF(d.left()+d.width()*f,d.bottom()))
            p.drawLine(QPointF(d.left(),d.top()+d.height()*f),QPointF(d.right(),d.top()+d.height()*f))
        for pt in (d.topLeft(),d.topRight(),d.bottomLeft(),d.bottomRight()):p.fillRect(QRectF(pt.x()-4,pt.y()-4,8,8),QColor('#e9bd69'))

class CropDialog(QDialog):
    def __init__(self,image,crop=None,parent=None):
        super().__init__(parent);self.setWindowTitle('裁剪画面');self.resize(920,650)
        layout=QVBoxLayout(self);row=QHBoxLayout();row.addWidget(QLabel('画面比例'))
        combo=QComboBox();self.ratios=RATIOS+[('原画面比例',(image.width(),image.height()))]
        for label,value in self.ratios:combo.addItem(label,value)
        row.addWidget(combo);row.addStretch();layout.addLayout(row)
        self.canvas=CropCanvas(image,crop);layout.addWidget(self.canvas,1)
        layout.addWidget(QLabel('按住左键框选；拖动四角调整大小，框内拖动可移动，框外拖动可重新框选。'))
        self.info=QLabel();layout.addWidget(self.info)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText('应用裁剪');self.buttons.button(QDialogButtonBox.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);layout.addWidget(self.buttons)
        combo.currentIndexChanged.connect(lambda i:self.canvas.set_ratio(self.ratios[i][1]))
        self.canvas.changed.connect(self.update_info);self.update_info()
    def crop(self):return pixel_rect(self.canvas.selection,self.canvas.image.width(),self.canvas.image.height(),self.canvas.ratio)
    def update_info(self):
        crop=self.crop();self.buttons.button(QDialogButtonBox.Ok).setEnabled(crop is not None)
        if not crop:self.info.setText('选区太小，请扩大范围。');return
        x,y,w,h=crop
        label,ratio=min(RATIOS[1:],key=lambda item:abs(math.log((w/h)/(item[1][0]/item[1][1]))))
        suffix=f'锁定比例 {self.canvas.ratio[0]}:{self.canvas.ratio[1]}' if self.canvas.ratio else f'常用比例建议：{label}；可在上方选择并锁定'
        self.info.setText(f'导出尺寸 {w} × {h} · {suffix}')
