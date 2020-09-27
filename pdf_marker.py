# GPL v3 or later
# author: Nic Freeman

from PyQt5 import QtGui, QtCore, QtWidgets
from PyQt5.QtCore import Qt
from PIL import Image
Image.MAX_IMAGE_PIXELS = 933120000
import pdf2image, img2pdf 
import numpy as np
import itertools
import os, sys, shutil
import datetime
import pickle, json, glob
import logging
import traceback

#import cProfile
#from pytictoc import TicToc
#t = TicToc()

loggingMode = logging.INFO
logging.basicConfig(filename='pdf_marker.log', 
					format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
					datefmt='%m-%d %H:%M:%S',
					filemode='a',
					level=loggingMode)
console = logging.StreamHandler()
console.setLevel(loggingMode)
console.setFormatter(logging.Formatter('%(levelname)-8s %(message)s'))
logging.getLogger('').addHandler(console)

scripts_dir = os.path.join(".","1_scripts")
workings_dir = os.path.join(".","2_working")
outputs_dir = os.path.join(".","3_outputs")

class Mark:
	def __init__(self, type, x, y, w, h, score=None, posList=None):
		self.type = type
		self.x = int(x)
		self.y = int(y)
		self.h = int(h) 
		self.w = int(w)
		self.posList = posList # list of QPointF
		self.score = score
		
	def __repr__(self):
		return "type:%s x:%s y:%s h:%s w:%s score:%s" % (self.type, self.x, self.y, self.h, self.w, self.score)

class MarkScheme:
	def __init__(self, file):
		# parse json description of mark scheme structure
		# format example: [["a 2", "b 5"], [". 8]]
		with open(file, "r") as f:
			paper = json.load(f)
		self.qs_max = []
		self.part_qs_max = []
		self.part_qs_str = []
		i = 0
		for i in range(len(paper)):
			question = paper[i]
			m_q = 0
			part_max = []
			part_str = []
			for part_q in question:
				label, marks = part_q.split(" ")
				m = int(marks)
				m_q += m
				part_max.append(m)
				part_str.append(label)
			self.qs_max.append(m_q)
			self.part_qs_max.append(part_max)
			self.part_qs_str.append(part_str)
		assert(len(self.qs_max)==len(self.part_qs_max))
			
		self.nFullMarks = np.sum(self.qs_max)
		self.fullMarksStr = "" 
		for i in range(len(self.qs_max)):
			self.fullMarksStr += "Q{:<2}:  {:<2}  {:<20}".format(i+1, np.sum(self.part_qs_max[i]), str(self.part_qs_max[i])) + "\n"

class Candidate:
	def __init__(self, dir):
		self.dir = dir
		self.name = os.path.split(dir)[-1]
		self.LoadMarks()
		
	def LoadMarks(self):
		with open(os.path.join(self.dir, "marks.pickle"), "rb") as f:
			self.marks = pickle.load(f)
	
	def SaveMarks(self):
		with open(os.path.join(self.dir, "marks.pickle"), "wb") as f:
			pickle.dump(self.marks, f)
	
	def TallyMarks(self):
		sorted_marks = []
		for i in range(len(self.marks)):
			sorted_marks.append(sorted(self.marks[i], key=lambda x: x.y))
		tally = 0
		for i in range(len(sorted_marks)):
			for mark in sorted_marks[i]:
				if mark.type=="score":
					tally += mark.score
				if mark.type=="tally":
					mark.score = tally
					tally = 0
		self.marks = sorted_marks
		
	def CollateMarks(self):
		self.TallyMarks() # we need them sorted, might as well tally too
		qs = []
		part_qs = [[]]
		for i in range(len(self.marks)):
			for mark in self.marks[i]:
				if mark.type=="score":
					part_qs[-1].append(mark.score)
				if mark.type=="tally":
					qs.append(mark.score)
					part_qs.append([])
		return qs, part_qs
	
	def CheckMarks(self, ms):
		qs, part_qs = self.CollateMarks()
					
		# visual comparison for user
		score = np.sum(qs, dtype=int)	
		label_text = ""
		lines = 0
		for i in range(len(qs)):
			label_text += "Q{:<2}:  {:<2}  {:<20}".format(i+1, np.sum(part_qs[i]), str(part_qs[i])) + "\n"
			lines += 1
		if len(part_qs[-1]) > 0:
			i = len(qs)
			label_text += "Q{:<2}:  {:<2}  {:<20}".format(i+1, "- ", str(part_qs[i])) + "\n" # part marks after last tally point
			lines += 1
		for i in range(len(ms.qs_max)-lines):
			label_text += "\n"
			
		# formal consistency check, in order helpful to user
		status = "Incomplete:\n  "
		# notify if too many qs
		if len(qs) > len(ms.qs_max):
			status += "Too many questions (%d vs %d)" % (len(qs), len(ms.qs_max))
			return checked, score, label_text, status		
		if len(part_qs) > len(ms.qs_max) and len(part_qs[-1])>0:
			status += "Part marks after final tally point"
			return False, score, label_text, status	
		part_qs.pop()
		# notify first question with too many part qs 
		for i in range(len(part_qs)):
			if len(part_qs[i]) > len(ms.part_qs_max[i]):
				status += "Q%d too many parts (%d vs %d)" % (i+1, len(part_qs[i]), len(ms.part_qs_max[i]))
				return False, score, label_text, status	
		# notify first part mark above max
		for i in range(len(part_qs)):
			for j in range(len(part_qs[i])):
				if part_qs[i][j] > ms.part_qs_max[i][j]:
					status += "Q%d part %d exceeds max (%d/%d)" % (i+1, j+1, part_qs[i][j], ms.part_qs_max[i][j])
					return False, score, label_text, status	
		# notify first question with too few part qs 
		for i in range(len(part_qs)):
			if len(part_qs[i]) < len(ms.part_qs_max[i]):
				status += "Q%d too few parts (%d vs %d)" % (i+1, len(part_qs[i]), len(ms.part_qs_max[i]))
				return False, score, label_text, status	
		# notify if too few qs
		if len(qs) < len(ms.qs_max):
				status += "Too few questions (%d vs %d)" % (len(qs), len(ms.qs_max))
				return False, score, label_text, status	
		# now check strikes		
		for i in range(len(self.marks)):
			found_strike = False
			for mark in self.marks[i]:
				if mark.type=="strike":
					found_strike = True
					break
			if not found_strike:
				status += "Strike missing on page %d" % (i+1)
				return False, score, label_text, status				
		# all good
		for i in range(len(qs)):
			assert(qs[i]==np.sum(part_qs[i]))
		return True, score, label_text, "Complete.\n\n"	
			
	def GetPagePath(self, i):
		return os.path.join(self.dir, "%03d"%(i)+".jpg")
	
	
class PrettyWidget(QtWidgets.QWidget):
	def __init__(self, parent=None):
		QtWidgets.QWidget.__init__(self, parent=parent)
		self.showMaximized()		
		self.setWindowTitle('Pdf Marker')
		self.installEventFilter(self)
		
		self.candidateDirs = []
		self.curCandidate = None # current candidate
		self.curPage = None # integer, current page of candidate
		
		self.curPixmapBG = None # current page without annotations
		self.curPixMapRatio = 1 # resize ratio of background pixmap to screen space
		self.marginX = 300 
				
		self.lastTabletEventTime = datetime.datetime.now() 
		self.tabletPainter = None # exists during tablet input
		self.tabletPenSize = 5
		self.tabletEventPosList = None
		
		self.configFile = os.path.join(".","config.pickle")
		
		logging.info("Initializing")
		self.LoadMarkScheme()		
		self.InitUI()
		self.LoadCandidates()
		
		self.show()
		
	def InitUI(self):
		self.loadScriptsButton = QtWidgets.QPushButton("Load scripts", self)
		self.loadScriptsButton.setToolTip("load in the scripts, ignoring any that already have working directories")
		self.loadScriptsButton.move(5,5)		
		self.loadScriptsButton.clicked.connect(self.LoadScripts)
		self.loadScriptsButton.show()

		self.outputScriptsButton = QtWidgets.QPushButton("Output scripts", self)
		self.outputScriptsButton.setToolTip("write out the annotated scripts, with csv marks if a markscheme was used")
		self.outputScriptsButton.move(5,5+self.loadScriptsButton.height())		
		self.outputScriptsButton.clicked.connect(self.OutputScripts)
		self.outputScriptsButton.show()
		
		self.forwardPageButton = QtWidgets.QPushButton(" > ", self)
		self.forwardPageButton.setToolTip("go back one page")
		self.forwardPageButton.clicked.connect(self.ForwardPage)
		self.backwardPageButton = QtWidgets.QPushButton(" < ", self)
		self.backwardPageButton.setToolTip("go forwards one page")
		self.backwardPageButton.clicked.connect(self.BackwardPage)

		self.progressLB = QtWidgets.QLabel(self)
		self.progressLB.setAlignment(Qt.AlignLeft)
		self.progressLB.setStyleSheet("font: 12pt Consolas")
		self.progressLB.move(10+self.loadScriptsButton.width(),5)
		self.progressLB.resize(200, self.loadScriptsButton.height())
		
		self.imgLB = QtWidgets.QLabel(self)		
		self.textLB = QtWidgets.QLabel(self)
		self.textLB.setAlignment(Qt.AlignLeft)
		
	def LoadMarkScheme(self):			
		self.markScheme = None
		file = os.path.join(".", "fullmarks.json")
		if os.path.exists(file):
			try:
				self.markScheme = MarkScheme(file) 
				logging.info("Loaded mark scheme, %d questions, total %d marks" % (len(self.markScheme.qs_max), np.sum(self.markScheme.qs_max)))
			except Exception as e:
				error_msg = "Failed to load mark scheme: %s" % str(e)
				logging.error(error_msg)
		else:
			logging.info("No mark scheme present")
		
	@QtCore.pyqtSlot()
	def LoadScripts(self):
		logging.info("Loading scripts")
		x_dim, y_dim = (2480,3508)
		if not os.path.exists(scripts_dir):
			logging.error("Scripts not found")
			return
		if not os.path.exists(workings_dir):
			os.mkdir(workings_dir)
		files = glob.glob(os.path.join(scripts_dir, "*.pdf"))
		self.progressLB.show()
		self.progressLB.setText("Processing... (%d/%d)" % (0, len(files)))
		QtWidgets.QApplication.processEvents()
		for i in range(len(files)):
			filename_pdf = files[i]
			logging.info("Processing '%s' (%d/%d)" % (filename_pdf, i+1, len(files)))
			try:
				candidate_name = os.path.split(filename_pdf)[1][:-4]
				candidate_dir = os.path.join(workings_dir, candidate_name)
				pages = pdf2image.convert_from_path(filename_pdf, 500)
				if os.path.exists(candidate_dir):
					logging.info("Candidate directory for '%s' already exists, skipping." % filename_pdf)
					continue
				else:
					os.mkdir(candidate_dir)
				marks = []
				for j in range(len(pages)):
					marks.append([])
				with open(os.path.join(candidate_dir, "marks.pickle"), 'wb') as f:
					pickle.dump(marks, f)
				candidate = Candidate(candidate_dir)
				for j in range(len(pages)):
					pages[j].thumbnail((x_dim,y_dim), Image.ANTIALIAS)
					pages[j].save(candidate.GetPagePath(j))
			except Exception as e:
				logging.error("Failed to load script from  '%s': %s" % (filename_pdf, str(e)))
			self.progressLB.setText("Processing... (%d/%d)" % (i+1, len(files)))
			QtWidgets.QApplication.processEvents()
		logging.info("Done loading")
		self.progressLB.hide()
		self.LoadCandidates()
	
	def LoadCandidates(self):
		self.candidateDirs = glob.glob(os.path.join(workings_dir,"*"))
		if len(self.candidateDirs)==0:
			logging.info("No candidates found, you probably need to load the scripts in")
			return
		
		if os.path.exists(self.configFile):
			with open(self.configFile, "rb") as f:
				config = pickle.load(f)			
			self.SetCandidatePage(config["candidate"], config["page"])
			return
		self.SetCandidatePage(self.candidateDirs[0], 0)
	
	def SetCandidatePage(self, dir, n):
		# ALL page changes go through here
		logging.debug("Set candidate page: %s %d" % (dir, n))
		if dir not in self.candidateDirs:
			logging.error("Candidate not found: %s" % (dir))
			return
		if not self.curCandidate or dir != self.curCandidate.dir:
			self.curCandidate = Candidate(dir)
		if n<-1 or n>=len(self.curCandidate.marks):
			logging.error("Attempt to set invalid candidate page: %s, %d" % (self.curCandidate.name, n))
			return
		self.curPage = n if n>=0 else len(self.curCandidate.marks)-1
		
		self.curPixmapBG = QtGui.QPixmap(self.curCandidate.GetPagePath(self.curPage))
		self.UpdatePixmap()

		config = {"candidate":self.curCandidate.dir, "page":self.curPage}
		with open(self.configFile, "wb") as f:
			pickle.dump(config, f)			
	
	def UpdatePixmap(self):
		if not self.curPixmapBG:
			return		
		logging.debug("Pixmap update")
		self.SetGeometry()
		
		blankPixmap = QtGui.QPixmap(self.curPixmapBG.width(), self.curPixmapBG.height())
		blankPixmap.fill(QtCore.Qt.transparent)
		marksPixmap = self.CreateMarksPixMap(self.curPixmapBG, self.curCandidate.marks[self.curPage])	
		canvasPainter = QtGui.QPainter(blankPixmap)
		canvasPainter.setRenderHint(QtGui.QPainter.Antialiasing)
		canvasPainter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)	
		canvasPainter.drawPixmap(blankPixmap.rect(), self.curPixmapBG)
		canvasPainter.drawPixmap(blankPixmap.rect(), marksPixmap)
		canvasPainter.end()
		
		self.imgLB.setPixmap(blankPixmap.scaled(self.imgLB.size(), QtCore.Qt.IgnoreAspectRatio, transformMode=QtCore.Qt.SmoothTransformation))	
		self.imgLB.show()	
		
		label_text = "Candidate: %d/%d \n" % (self.candidateDirs.index(self.curCandidate.dir)+1, len(self.candidateDirs))
		label_text += "Page: %d/%d \n\n\n" % (self.curPage+1, len(self.curCandidate.marks))	
		if self.markScheme:
			_, score, part_score_str, status = self.curCandidate.CheckMarks(self.markScheme)
			label_text += "Score: %d/%d = %0.f%%\n" % (score, self.markScheme.nFullMarks, 100*score/self.markScheme.nFullMarks)
			label_text += part_score_str + "\n\n"
			label_text += status + "\n\n"
			label_text += "Max: %d\n" % self.markScheme.nFullMarks
			label_text += self.markScheme.fullMarksStr
		self.textLB.setText(label_text)
		
	def SetGeometry(self):
		x_window = self.geometry().width()
		y_window = self.geometry().height()
		if x_window > 1.5*y_window: # landscape
			x_ratio = float(x_window*0.5) / float(self.curPixmapBG.width())
			y_ratio = float(y_window*0.99) / float(self.curPixmapBG.height())
			ratio = min(x_ratio, y_ratio)
			self.curPixMapRatio = ratio
			x_img = self.curPixmapBG.width() * ratio
			y_img = self.curPixmapBG.height() * ratio	
			self.imgLB.resize(int(x_img), int(y_img))
			self.imgLB.move(int((x_window - x_img) / 2),int((y_window - y_img) / 2))
			self.textLB.resize(int(x_window*0.25), int(y_window*0.6))
			self.textLB.move(int(x_window*0.1), int(y_window*0.25))
			fontSize = min(15, int(self.textLB.width()/35))
			self.textLB.setFont(QtGui.QFont("Consolas", fontSize))
			self.textLB.setText(self.textLB.text())
			self.textLB.show() 
		else: #portrait
			x_ratio = float(x_window*0.9) / float(self.curPixmapBG.width())
			y_ratio = float(y_window*0.88) / float(self.curPixmapBG.height())
			ratio = min(x_ratio, y_ratio)
			self.curPixMapRatio = ratio
			x_img = self.curPixmapBG.width() * ratio
			y_img = self.curPixmapBG.height() * ratio	
			self.imgLB.resize(int(x_img), int(y_img))
			self.imgLB.move(int((x_window - x_img) / 2),int((y_window - y_img) * 9/10))
			self.textLB.hide()				
		w = self.forwardPageButton.width()
		h = self.loadScriptsButton.height() 
		self.backwardPageButton.move(x_window-w*2-5, 5)
		self.backwardPageButton.resize(w, h*2)
		self.backwardPageButton.show()
		self.forwardPageButton.move(x_window-w-10, 5)
		self.forwardPageButton.resize(w, h*2)
		self.forwardPageButton.show()


			
	def CreateMarksPixMap(self, pixmap_bg, marks, suppressStrikes=False):
		pixmap = QtGui.QPixmap(pixmap_bg.width(), pixmap_bg.height())
		pixmap.fill(QtCore.Qt.transparent)
		painter = QtGui.QPainter(pixmap)
		painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
		painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)	
		painter.setPen(QtGui.QPen(Qt.red,  4, Qt.SolidLine))
		# mark types: strike, score, tally, justify, circle, leftarrow, rightarrow
		for mark in marks:
			if mark.type=="strike" and not suppressStrikes:
				painter.setOpacity(0.5)
				w = self.curPixmapBG.width() 
				h = self.curPixmapBG.height()
				painter.drawLine(int(w/2/0.9), int(h*0.02), int(w/2*0.9), int(h*0.98))								
				painter.setOpacity(1)
			elif mark.type=="circle":
				painter.drawEllipse(int(mark.x-mark.w/2), int(mark.y-mark.h/2), mark.w, mark.h)
			elif mark.type=="justify":
				painter.setFont(QtGui.QFont("sanserif", int(mark.h*0.5)))
				rect = QtCore.QRect(int(mark.x-mark.w/2), int(mark.y-mark.h/2), mark.w, mark.h)
				painter.drawText(rect, Qt.AlignCenter, "justify")			
			elif mark.type=="score" or mark.type=="tally":
				painter.setFont(QtGui.QFont("sanserif", int(mark.h*0.8)))
				rect = QtCore.QRect(int(mark.x-mark.w/2), int(mark.y-mark.h/2), mark.w, mark.h)
				painter.drawText(rect, Qt.AlignCenter, str(int(mark.score)))
				if mark.type=="tally":
					painter.drawRect(rect)
			elif mark.type=="leftarrow":
				painter.drawLine(int(mark.x-mark.w/2), mark.y, int(mark.x+mark.w/2), mark.y)
				painter.drawLine(int(mark.x-mark.w/2+mark.h/4), int(mark.y-mark.h/4), int(mark.x-mark.w/2), mark.y)
				painter.drawLine(int(mark.x-mark.w/2+mark.h/4), int(mark.y+mark.h/4), int(mark.x-mark.w/2), mark.y)
			elif mark.type=="rightarrow":
				painter.drawLine(int(mark.x-mark.w/2), mark.y, int(mark.x+mark.w/2), mark.y)
				painter.drawLine(int(mark.x+mark.w/2-mark.h/4), int(mark.y-mark.h/4), int(mark.x+mark.w/2), mark.y)
				painter.drawLine(int(mark.x+mark.w/2-mark.h/4), int(mark.y+mark.h/4), int(mark.x+mark.w/2), mark.y)
			elif mark.type=="touch":
				painter.setPen(QtGui.QPen(Qt.red,  self.tabletPenSize, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
				for i in range(len(mark.posList)-1):
					x1 = mark.posList[i].x()
					y1 = mark.posList[i].y()
					x2 = mark.posList[i+1].x()
					y2 = mark.posList[i+1].y()
					painter.drawLine(int(x1), int(y1), int(x2), int(y2))
				painter.setPen(QtGui.QPen(Qt.red,  4, Qt.SolidLine))
		# margin		
		if self.markScheme:
			painter.setPen(QtGui.QPen(Qt.red,  4, Qt.DashLine))
			painter.drawLine(self.marginX, 0, self.marginX, int(self.height()/self.curPixMapRatio))
		painter.end()
		return pixmap

	@QtCore.pyqtSlot()
	def ForwardPage(self):
		self.IncrementPage(1, False)

	@QtCore.pyqtSlot()
	def BackwardPage(self):
		self.IncrementPage(-1, False)
	
	def eventFilter(self, obj, event):
		if event.type() == QtCore.QEvent.MouseButtonPress:	
			if self.tabletPainter or datetime.datetime.now()-self.lastTabletEventTime < datetime.timedelta(seconds=0.1): 
				logging.debug("Suppressed QEvent.MouseButtonPress")
				return True # some QEvent.TabletPress get duplicatedsd as QEvent.MouseButtonPress >_>
			self.MousePressEvent(event)
		elif event.type() == QtCore.QEvent.MouseButtonDblClick:
			if self.tabletPainter or datetime.datetime.now()-self.lastTabletEventTime < datetime.timedelta(seconds=0.1): 
				logging.debug("Suppressed QEvent.MouseButtonDblClick")
				return True 
			self.MousePressEvent(event)		
		elif event.type() == QtCore.QEvent.KeyPress:	
			self.KeyPressEvent(event)
		elif event.type() == QtCore.QEvent.TabletPress:	
			self.lastTabletEventTime = datetime.datetime.now()
			self.tabletControl = True
			self.TabletPressEvent(event)
		elif event.type() == QtCore.QEvent.TabletMove:	 
			self.lastTabletEventTime = datetime.datetime.now()
			self.TabletMoveEvent(event)
		elif event.type() == QtCore.QEvent.TabletRelease:	
			self.lastTabletEventTime = datetime.datetime.now()
			self.tabletControl = False
			self.TabletReleaseEvent(event)
		else:
			return super(PrettyWidget, self).eventFilter(obj, event)
		return True
		
	def TabletPressEvent(self, event):
		# touch marks are drawn here in screen space, then converted to underlying image size in TabletReleaseEvent
		x = event.x() - self.imgLB.x()
		y = event.y() - self.imgLB.y()
		if x >= self.imgLB.width() or y >= self.imgLB.height():
			return True
		self.tabletPainter = QtGui.QPainter(self.imgLB.pixmap())
		self.tabletPainter.setRenderHint(QtGui.QPainter.Antialiasing, True)
		self.tabletPainter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)	
		pen_size = max(1, int(min(self.imgLB.height(), self.imgLB.width())/300)) # magic
		self.tabletPainter.setPen(QtGui.QPen(Qt.red, self.tabletPenSize*self.curPixMapRatio, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
		self.tabletEventPosList = [QtCore.QPointF(x,y)] # list for possible future use e.g bezier
		logging.debug("Tablet painter is on")
	
	def TabletMoveEvent(self, event):
		if not self.tabletPainter or not self.tabletEventPosList:
			return True
		x = event.x() - self.imgLB.x()
		y = event.y() - self.imgLB.y()
		if x >= self.imgLB.width() or y >= self.imgLB.height():
			return True
		last_x = self.tabletEventPosList[-1].x()
		last_y = self.tabletEventPosList[-1].y()
		self.tabletPainter.drawLine(int(x), int(y), int(last_x), int(last_y))
		self.update()
		self.tabletEventPosList.append(QtCore.QPointF(x,y))
	
	def TabletReleaseEvent(self, event):
		if not self.tabletPainter or not self.tabletEventPosList:
			return True
		self.tabletPainter.end()
		self.tabletPainter = None
		logging.debug("Tablet painter is off")
		mark = Mark("touch", -1, -1, -1, -1, None, self.ScaleEventList(self.tabletEventPosList))
		self.curCandidate.marks[self.curPage].append(mark)
		logging.debug("Added touch mark, first pos (%f,%f)" % (self.tabletEventPosList[0].x(), self.tabletEventPosList[0].y()))
		self.tabletEventPosList = None
		self.UpdatePixmap()
		
	def ScaleEventList(self, l):
		return [QtCore.QPointF(p.x()/self.curPixMapRatio,p.y()/self.curPixMapRatio) for p in l]	
		
	def MousePressEvent(self, event):
		global_x = event.pos().x()
		global_y = event.pos().y()
		x = global_x - self.imgLB.x()
		y = global_y - self.imgLB.y()
		if x >= self.imgLB.width() or y >= self.imgLB.height():
			return
		x /= self.curPixMapRatio
		y /= self.curPixMapRatio
		x = int(x)
		y = int(y)
		margin = self.markScheme and (x <= self.marginX)  
		if margin:
			x = self.marginX/2
		marks = self.curCandidate.marks[self.curPage]
		mark = self.ExtractMarkAtLoc(x,y, marks)
		old_mark = mark
		shift = (event.modifiers() == QtCore.Qt.ShiftModifier)
		scale = self.marginX # ugh, but its not so silly
		if not mark:
			# add new mark
			if margin:			
				if event.button()==1: # left mouse
					count = 5 if shift else 1
					mark = Mark("score", x, y, scale/3*1.25, scale/3, count)
				elif event.button()==2: # left mouse
					mark = Mark("score", x, y, scale/3*1.25, scale/3, 0)
				elif event.button()==4: # mid mouse
					mark = Mark("tally", x, y, scale/3*1.25, scale/3, -1)
			else:
				if event.button()==1: # left mouse
					mark = Mark("circle", x, y, scale/3, scale/3)
				if event.button()==2: # right mouse
					mark = Mark("justify", x, y, scale/2, scale/3.5)
				elif event.button()==16: # forward mouse
					mark = Mark("rightarrow", x, y, scale/2, scale/3)
				elif event.button()==8: # backwards mouse
					mark = Mark("leftarrow", x, y, scale/2, scale/3)
		else:
			# mark exists here already
			if margin and mark.type=="score":			
				count = 5 if shift else 1
				if event.button()==1: # left mouse
					mark.score += count
				elif event.button()==2: # right mouse
					mark.score -= count
					if mark.score<0:
						mark = None
			else:
				if mark.type=="circle":
					incr_scale = 2
					if event.button()==1: # left mouse
						mark.h *= incr_scale
						mark.w *= incr_scale
					elif event.button()==2: # right mouse
						mark.h /= incr_scale
						mark.w /= incr_scale
						if mark.h<=150 or mark.w<=150:
							mark = None
				else:
					mark = None
		if mark:
			marks.append(mark)		
		if mark:
			if old_mark: logging.debug("Modified mark: %s -> %s" % (old_mark,mark))
			else: logging.debug("Added mark: %s" % mark)
		else:
			if old_mark: logging.debug("Removed mark: %s" % old_mark)
		self.curCandidate.TallyMarks()
		self.curCandidate.SaveMarks()
		self.UpdatePixmap()		
		
	def IsMarkAtLoc(self, mark, x, y):
		if mark.type=="strike":
			return False
		hit = False
		if mark.type=="circle":
			hit = ((mark.x-x)**2 + (mark.y-y)**2 <= (mark.h/2)**2)
		elif mark.type=="touch":
			for p in mark.posList:
				r = 30 # magic
				if (x-p.x())**2 + (y-p.y())**2 <= r**2:
					hit = True
					break
		else:
			hit = (abs(mark.x-x)<mark.h/2 and abs(mark.y-y)<mark.w/2)
		return hit
		
	def ExtractMarkAtLoc(self, x,y, marks):
		# get the (first) mark covering (x,y)
		_mark = None
		for i in range(len(marks)):
			mark = marks[i]
			if self.IsMarkAtLoc(mark, x, y):
				_mark = mark
				del marks[i]
				return _mark	
				
	def KeyPressEvent(self, event):
		key = event.key()		
		shift = (event.modifiers() == QtCore.Qt.ShiftModifier)
		control = (event.modifiers() == QtCore.Qt.ControlModifier)
		step = 1 if not control else 5
		if key == QtCore.Qt.Key_Escape:
			self.close()
		elif key == QtCore.Qt.Key_Right or key == QtCore.Qt.Key_D:
			self.IncrementPage(step, shift)
		elif key == QtCore.Qt.Key_Left or key == QtCore.Qt.Key_A:
			self.IncrementPage(-step, shift)
		elif key == QtCore.Qt.Key_W:
			self.SkipToFirstUncheckedCandidate()
		elif key == QtCore.Qt.Key_S:
			self.ToggleStrike()
			self.curCandidate.SaveMarks()
			self.UpdatePixmap()
		elif key == QtCore.Qt.Key_C:
			self.ClearCurrentPage()
	
	def ClearCurrentPage(self):
		if not self.curCandidate:
			return
		self.curCandidate.marks[self.curPage] = []
		self.UpdatePixmap()
		logging.debug("Removed all marks on current page")
	
	def ToggleStrike(self):
		marks = self.curCandidate.marks[self.curPage]
		strike_idx = None
		for i in range(len(marks)):
			mark = marks[i]
			if mark.type=="strike":
				strike_idx = i
				break
		if strike_idx != None:
			del marks[strike_idx]
		else:
			marks.append(Mark("strike",-1,-1,-1,-1))
		logging.debug("Strike toggled, state=%r" % (strike_idx==None))

	def IncrementPage(self, step, per_candidate, candidate_first_page=True):
		if per_candidate:
			target_idx = self.candidateDirs.index(self.curCandidate.dir) + step
			target_idx = np.clip(target_idx, 0, len(self.candidateDirs)-1)
			dir = self.candidateDirs[target_idx]
			if dir != self.curCandidate.dir: # don't reset candidatePage to 0 at top-most end
				candidatePage = 0 if candidate_first_page else -1
				self.SetCandidatePage(dir, candidatePage)
			return
		target_page = self.curPage + step
		if target_page<0:
			self.IncrementPage(-1, True, False)
			return
		elif target_page>=len(self.curCandidate.marks):
			self.IncrementPage(1, True, True)
			return
		self.SetCandidatePage(self.curCandidate.dir, target_page)
		
	def SkipToFirstUncheckedCandidate(self):
		if not self.markScheme:
			return True
		for dir in self.candidateDirs:
			candidate = Candidate(dir)
			good, _,_,_ = candidate.CheckMarks(self.markScheme)
			if not good:
				self.SetCandidatePage(dir, 0)
				return False
		return True				
	
	@QtCore.pyqtSlot()
	def OutputScripts(self):
		# check
		if self.markScheme:
			if not self.SkipToFirstUncheckedCandidate():
				return
				
		# write the pdfs
		if	os.path.exists(outputs_dir):
			shutil.rmtree(outputs_dir)
		os.mkdir(outputs_dir)
		self.progressLB.show()
		self.progressLB.setText("Processing... (%d/%d)" % (0, len(self.candidateDirs)))
		QtWidgets.QApplication.processEvents()
		for i in range(len(self.candidateDirs)):
			dir = self.candidateDirs[i]
			candidate = Candidate(dir)
			out_working_dir = os.path.join(dir,"output") 
			if	os.path.exists(out_working_dir):
				shutil.rmtree(out_working_dir)
			os.mkdir(out_working_dir)
			for j in range(len(candidate.marks)):
				bgPixmap = QtGui.QPixmap(candidate.GetPagePath(j))
				marksPixmap = self.CreateMarksPixMap(bgPixmap, candidate.marks[j])
				canvasPainter = QtGui.QPainter(bgPixmap)
				canvasPainter.setRenderHint(QtGui.QPainter.Antialiasing)
				canvasPainter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceOver)	
				canvasPainter.drawPixmap(bgPixmap.rect(), marksPixmap)
				canvasPainter.end()
				out_path = os.path.join(out_working_dir, "%03d"%(j)+".jpg")
				bgPixmap.save(out_path, "jpg")
			self.progressLB.setText("Processing... (%d/%d)" % (i+1, len(self.candidateDirs)))
			QtWidgets.QApplication.processEvents()
		
			marked_jpgs = glob.glob(os.path.join(out_working_dir,"*"))
			pdf = img2pdf.convert(marked_jpgs)
			with open(os.path.join(outputs_dir, candidate.name+".pdf"), "wb") as f:
				f.write(pdf)
			logging.info("Wrote marked pdf for '%s' (%d/%d)" % (candidate.name, i+1, len(self.candidateDirs)))
		self.progressLB.hide()
		
		if not self.markScheme:
			return
		
		# write the csvs
		questions_str = ""
		part_questions_str = ""
		for i in range(len(self.markScheme.qs_max)):
			questions_str += "Q" + str(i+1) + "," 
			for label in self.markScheme.part_qs_str[i]:
				part_questions_str += str(i+1) + label + ","
		
		csv_tots	= "Candidate,Total,\n"
		csv_qs		= "Candidate, " + questions_str + "Total,\n"
		csv_part_qs = "Candidate," + part_questions_str + "Total,\n"
		csv_exam	= "Candidate," + questions_str + "Total,All Marked,Total Checked,\n"
		
		for i in range(len(self.candidateDirs)):
			dir = self.candidateDirs[i]
			candidate = Candidate(dir)
			qs, part_qs = candidate.CollateMarks()
			qs_str = ",".join(str(x) for x in qs)
			part_qs_str = ",".join(str(x) for x in list(itertools.chain.from_iterable(part_qs)))		
			tot_str = str(np.sum(qs, dtype=int))
			
			csv_tots += candidate.name + "," + tot_str + ",\n"
			csv_qs += candidate.name + "," + qs_str + "," + tot_str + ",\n"
			csv_part_qs += candidate.name + "," + part_qs_str + "," + tot_str + ",\n"
			csv_exam += candidate.name + "," + qs_str + "," + tot_str + ",y,y,\n"
			
		with open(os.path.join("./", "out_totals.csv"), "w") as csv:
			csv.write(csv_tots)
		with open(os.path.join("./", "out_qs.csv"), "w") as csv:
			csv.write(csv_qs)
		with open(os.path.join("./", "out_part_qs.csv"), "w") as csv:
			csv.write(csv_part_qs)
		with open(os.path.join("./", "out_somas_upload_format.csv"), "w") as csv:
			csv.write(csv_exam)
		
		logging.info("Wrote csv files, output complete")

	def resizeEvent(self, event):
		if hasattr(self,"curCandidate"): # can occur before __init__
			self.UpdatePixmap()

	def closeEvent(self, event):
		if self.curCandidate:
			self.curCandidate.SaveMarks()
		logging.info("Shutdown")

		
def main():
	app = QtWidgets.QApplication(sys.argv)
	ex = PrettyWidget()
	app.exec_()

if __name__ == '__main__':
	main()
