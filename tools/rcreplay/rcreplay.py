#!/usr/bin/env python
# -*- coding: utf-8 -*-

#    Copyright (C) 2010 by RoboLab - University of Extremadura
#
#    This file is part of RoboComp
#
#    RoboComp is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    RoboComp is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with RoboComp.  If not, see <http://www.gnu.org/licenses/>.
#
debug = False
import sys, os, time, new, traceback, threading
try:
	import cPickle as pickle
except:
	import cpickle
import Ice
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.Qt import *
from ui_gui import Ui_ReplayMainWindow
from ui_frameskip import Ui_ReplayFrameskipMainWindow

# Get environment variables
ROBOCOMP = ''
SLICE_PATH = ''
try:
	ROBOCOMP = os.environ['ROBOCOMP']
except:
	print 'ROBOCOMP environment variable not set! Exiting.'
	sys.exit()
try:
	SLICE_PATH = os.environ['SLICE_PATH']
except:
	pass

def helpMsg(argv):
	print 'replayComp: Error: A configuration file must be specified.',
	if len(argv)>2: print 'And only one.',
	print '\ne.g.:  ', argv[0], 'replay.conf'
	print '       ', argv[0], '--Ice.Config=replay.conf'
	print '\ne.g.:  ', argv[0], 'replay.conf --frameskip'
	print '       ', argv[0], '--Ice.Config=replay.conf --frameskip'
	print 'The "frameskip" flag can be used to reduce the number of measures per second in a replayComp file.'
# Global communicator
argv = sys.argv
if len(argv)<2:
	helpMsg(argv)
elif len(argv)>2 and argv[2]!='--frameskip':
	helpMsg(argv)
elif argv[1].rfind('--Ice.Config=') != 0:
	argv[1] = '--Ice.Config='+argv[1]
try:
	global_ic = Ice.initialize(argv)
except Ice.FileException:
	print 'replayComp: Error: Make sure the file specified ('+argv[1][13:] + ') exists.'
	sys.exit(-1)
except:
	traceback.print_exc()

# Module import function
def importCode(path, name):
	filed = open(path, 'r')
	code = filed.read()
	filed.close()
	module = new.module(name)
	exec code in module.__dict__
	return module


################################################
## E X I T     M E S S A G E     W I D G E T  ##
################################################
class ReplayExitWindow(QDialog):
	def __init__(self, text, parent=None):
		QDialog.__init__(self, parent)
		self.label = QLabel(text, self)
		self.label.move(self.label.width()/2, self.label.height()/2)
		self.setFixedSize(self.label.width()*2, self.label.height()*2)
		self.setModal(True)
		self.label.show()
		self.show()
class ReplayExitMessage(QThread):
	def __init__(self, text, parent=None):
		QThread.__init__(self)
		self.widgetMessage = ReplayExitWindow(text, parent)
		self.widgetMessage.show()
		self.widgetMessage.label.show()
		self.stop = False
	def close(self):
		self.widgetMessage.close()
		self.stop = True
	def run(self):
		tick = 0
		while not self.stop:
			time.sleep(0.01)
			if tick%20 == 0:
				print '.',
			tick+=1

################################
## D U M M Y     W I D G E T  ##
################################
class DummyWidget(QLabel):
	def __init__(self, identifier, parent=None):
		QLabel.__init__(self, identifier, parent)
		self.show()
		self.measure = None
	def setMeasure(self, measure):
		self.measure = measure



################################
##  M E A S U R E      S E T  ##
################################
class ComponentMeasureSet(dict):
	def __init__(self, time):
		self.time = time
	def add(self, identifier, data):
		self[identifier] = data
	def __repr__(self):
		string = 'Measure<[\n'
		for i in self:
			string += '  ' + str(i) + ' ([' + str(type(self[i])) + '] ' + str(self[i]) + '), '
		string = string[:-2] + '\n]'
		return string
	def __str__(self):
		return repr(self)


###################
##  H E A D E R  ##
###################
class ReplayHeader:
	def __init__(self, aliases=[], mode='', filename='', cfgDict=dict()):
		self.index = list()
		self.set(aliases, mode, filename, cfgDict)
	def set(self, aliases, mode, filename, cfgDict):
		self.aliases = aliases
		self.mode = mode
		self.filename = filename
		self.cfgDict = cfgDict
	def __repr__(self):
		string = 'ReplayHeader:'
		string += '\n\tAliases ' + str(self.aliases)
		string += '\n\tMode    ' + str(self.mode)
		string += '\n\tFile    ' + str(self.filename)
		for i in self.cfgDict:
			string += '\n\t\t' + repr(self.cfgDict[i])
		return string
	def __str__(self):
		return repr(self)


#########################################
##  C O M P O N E N T     C O N F I G  ##
#########################################
class ReplayComponentConfig:
	def __init__(self, name, path, slicePath, module, worker_class, identifier):
		self.path = path
		self.slicePath = slicePath
		self.module = module
		self.worker_class = worker_class
		self.identifier = identifier
		self.configuration = None
	def setConfiguration(self, configuration):
		self.configuration = configuration
		self.worker_class.setConfiguration(self.configuration)
	def __repr__(self):
		return '<CODE:'+str(self.path)+', SLICE:'+str(self.slicePath)+', MODULE:'+str(self.module)+', WORKER:'+str(self.worker_class)+', ID:'+str(self.identifier)+', CFG:'+str(self.configuration)+']'
	def __str__(self):
		return repr(self)


###################
##  W R I T E R  ##
###################
class ReplayStorageWriter:
	def __init__(self, path):
		self.path = path
		global debug
		if debug: print 'Opening', self.path, 'with write permissions'
		self.wfile = open(self.path, 'wb')
		self.measures = 0
		# Alloc file space for the header pointer
		self.wfile.write('0'*15)
	def writeMeasure(self, measure):
		ret = self.wfile.tell()
		pickle.dump(measure, self.wfile, 2)
		self.measures+=1
		return ret
	def done(self, header):
		global debug
		if debug: print 'Header index length', len(header.index)
		for cfg in header.cfgDict.values():
			cfg.worker_class = None
			cfg.gui_class = None
			cfg.module = None
			header.cfgDict[cfg.identifier] = cfg
		print 'Writing header'
		header_pointer = self.wfile.tell()
		pickle.dump(header, self.wfile, 2)
		self.wfile.seek(0, os.SEEK_SET)
		self.wfile.write(str(header_pointer).zfill(15))
		self.wfile.close()
		print 'Written', self.measures, 'measures'

###################
##  R E A D E R  ##
###################
class ReplayStorageReader:
	def __init__(self, path):
		global debug
		if debug: print 'Opening', path, 'with read permissions'
		self.rfile = open(path, 'rb')
		self.header_pointer = int(self.rfile.read(15))
		self.rfile.seek(self.header_pointer, os.SEEK_SET)
		self.header = pickle.load(self.rfile)
		if debug:
			for identifier in self.header.cfgDict:
				print identifier
				print ' ', type(self.header.cfgDict[identifier].configuration), self.header.cfgDict[identifier].configuration
		self.rfile.seek(15, os.SEEK_SET)
		self.measures = 0
	def goto(self, idx):
		self.rfile.seek(self.header.index[idx], os.SEEK_SET)
		self.measures = idx
	def advance(self, units):
		self.goto(self.measures+units)
	def readMeasure(self):
		if self.header_pointer > self.rfile.tell():
			try:
				ret = pickle.load(self.rfile)
			except EOFError:
				raise 'end'
			except:
				raise 'end'
				traceback.print_exc()
			self.measures+=1
			return ret
		else:
			raise 'end'
	def eof(self):
		if self.header_pointer > self.rfile.tell():
			return False
		else:
			return True
	def done(self):
		self.rfile.close()


##############################
##   M A I N    C L A S S   ##
##############################
class ReplayCompIce(QThread, QObject):
	def readAliasProperty(self, alias, string):
		try:
			return global_ic.getProperties().getProperty(alias+'.'+string)
		except:
			traceback.print_exc()
			print 'Can\'t read '+string+' for component', alias
			sys.exit(1)
	def initialization(self, start=True):
		self.running = False
		self.finished = False
		self.speedup = 1.
		self.time = QTime.currentTime()
		self.status = 0;
		global global_ic
		try:
			#
			# Set global header parameters
			self.aliases = global_ic.getProperties().getProperty('Replay.Aliases').split(',')
			self.mode = global_ic.getProperties().getProperty('Replay.Mode').lower()
			self.filename = global_ic.getProperties().getProperty('Replay.File')
			if self.mode != 'replay' and self.mode != 'capture': raise 'Mode must be REPLAY or CAPTURE ('+self.mode+').'
			self.header = ReplayHeader(self.aliases, self.mode, self.filename, dict())
		except:
			traceback.print_exc()
			print 'Can\'t read global header parameters'
			sys.exit(1)
		#
		# Set plug-in specific parameters
		global debug
		if debug: print 'Aliases:', self.aliases
		cfgDict = dict()
		for alias in self.aliases:
			if debug: print '\nReading config for', alias
			name = self.readAliasProperty(alias, 'name')
			path = self.readAliasProperty(alias, 'codePath')
			identifier = self.readAliasProperty(alias, 'identifier')
			proxy = self.readAliasProperty(alias, 'proxy')
			slicePath = self.readAliasProperty(alias, 'slicePath')
			string_final = slicePath + ' -I' + ROBOCOMP + '/interfaces/ '
			for spath in SLICE_PATH.split(';'):
				if len(spath) > 0:
					string_final += ' -I' + spath
			string_final += ' --all'
			if debug: print 'slice2py string:', string_final
			Ice.loadSlice(string_final)
			module = importCode(path, name)

			self.header.mode = self.mode
			# handle plug-in as replay
			if self.header.mode == 'replay':
				adapter = global_ic.createObjectAdapter(alias)
				try:
					worker_class = module.getReplayClass()
				except:
					traceback.print_exc()
					print 'Can\'t get replay class. Check your module "getReplayClass()'
				try:
					adapter.add(worker_class, global_ic.stringToIdentity(name))
				except:
					print 'Can\'t add adapter.', name
				adapter.activate()
				cfg = ReplayComponentConfig(name, path, slicePath, module, worker_class, identifier)
				cfgDict[identifier] = cfg
			# handle plug-in as capture
			elif self.mode == 'capture':
				worker_class = module.getRecordClass(global_ic.stringToProxy(proxy))
				cfg = ReplayComponentConfig(name, path, slicePath, module, worker_class, identifier)
				cfg.configuration = cfg.worker_class.getConfiguration()
				cfgDict[identifier] = cfg
		if debug: print 'Done reading configuration'
		if debug: print cfgDict.keys()
		self.header.cfgDict = cfgDict

		if start:
			try:
				# R E P L A Y
				if self.mode == 'replay':
					self.reader = ReplayStorageReader(self.filename)
					for identifier in self.reader.header.cfgDict:
						cfgDict[identifier].configuration = self.reader.header.cfgDict[identifier].configuration
						cfgDict[identifier].worker_class.setConfiguration(cfgDict[identifier].configuration)
					self.reader.header.cfgDict = cfgDict
					self.header.index = self.reader.header.index
					self.sTimer = QTimer()
					self.sTimer.setSingleShot(True)
					self.connect(self.sTimer, SIGNAL('timeout()'), self.readMeasureSet)
				# C A P T U R E
				elif self.mode == 'capture':
					self.writer = ReplayStorageWriter(self.filename)
			except:
				traceback.print_exc()
				print 'Can\'t read '
				sys.exit(1)
	def run (self):
		self.initialization()
		if self.header.mode == 'replay':
			global debug
			if debug:
				for identifier in self.header.cfgDict:
					print identifier
					print ' ', type(self.header.cfgDict[identifier].configuration), self.header.cfgDict[identifier].configuration
			try:
				self.measureSet = self.reader.readMeasure()
			except:
				traceback.print_exc()
				print 'We could read the header but not a measure'
				sys.exit(1)
		self.running = True
		try:
			global_ic.waitForShutdown()
		except:
			traceback.print_exc()
			self.status = 1
	# write
	def writeMeasureSet(self):
		if self.finished:
			print 'calling WriteMeasureSet() when ReplayCompIce is already finished'
			return
		if self.mode == 'capture':
			measureSet = ComponentMeasureSet(self.time.msecsTo(QTime.currentTime()))
			for cfg in self.header.cfgDict.values():
				measureSet.add(cfg.identifier, cfg.worker_class.getMeasure())
			position = self.writer.writeMeasure(measureSet)
			self.header.index.append(position)
	# setSpeedup
	def setSpeedUp(self, newSpeedUp):
		self.speedup = newSpeedUp
		self.time = QTime.currentTime().addMSecs(-int(float(self.measureSet.time)/self.speedup))

	# read
	def readMeasureSet(self, force=False):
		if self.finished:
			print 'calling WriteMeasureSet() when ReplayCompIce is already finished'
			return False
		ret = False
		val = (self.measureSet.time)-self.time.msecsTo(QTime.currentTime())*self.speedup
		#print 'val', val
		#if val < -100 and self.measureSet.time > 100000:
			#try:
				#self.reader.advance(int(1))
				##self.reader.advance(int(val/(-30.))+1)
				#print 'Skipping frame'
			#except:
				#self.reader.goto(0)
				#self.time = QTime.currentTime()
			#force = True
		if force or (val < 0):
			for identifier in self.measureSet:
				self.header.cfgDict[identifier].worker_class.setMeasure(self.measureSet[identifier])
			try:
				self.measureSet = self.reader.readMeasure()
			except:
				print 'Starting over.'
				try:
					if self.reader.eof():
						self.reader.goto(0)
					else:
						self.reader.advance(int(1))
				except:
					print 'Could not re-read header'
					sys.exit(-1)
			ret = True
			force = False
		if ret: self.sTimer.start(1)
		return ret
	def goto(self, newIdx):
		self.reader.goto(newIdx)
		self.measureSet = self.reader.readMeasure()
		self.setSpeedUp(self.speedup)

	# done
	def done(self):
		if self.finished:
			print 'calling WriteMeasureSet() when ReplayCompIce is already finished'
			return
		if self.mode == 'capture':
			self.writer.done(self.header)
			self.finished = True
			sys.exit(0)

############################
##   G U I    C L A S S   ##
############################
class ReplayFrameskipUI(QMainWindow):
#
# Constructor
	def __init__(self):
		self.measures = 0
		self.writtenMeasures = 0
		QMainWindow.__init__(self)
		self.ice = ReplayCompIce()
		self.icerunning = False
		self.ice.start()
		while self.icerunning == False:
			try:
				while self.ice.running == False: time.sleep(0.05)
				self.icerunning = True
			except:
				time.sleep(0.05)
		self.ui = Ui_ReplayFrameskipMainWindow()
		self.ui.setupUi(self)
		self.ui.inputFile.setText(global_ic.getProperties().getProperty('Replay.File'))
		self.connect(self.ui.fileButton, SIGNAL('clicked()'), self.startConversion)
		for i in range(3):
			self.ui.tabWidget.setTabEnabled(i, False)
		self.ui.tabWidget.setTabEnabled(0, True)
		self.ui.tabWidget.setCurrentIndex(0)
	def startConversion(self):
		self.entrada = None
		self.salida = None
		try:
			self.entrada = open(str(self.ui.inputFile.text()), 'r')
			self.salida = open(str(self.ui.outputFile.text()), 'w')
			self.mps = self.ui.mps.value()
			for i in range(3):
				self.ui.tabWidget.setTabEnabled(i, False)
			self.ui.tabWidget.setTabEnabled(1, True)
			self.ui.tabWidget.setCurrentIndex(1)
			self.disconnect(self.ui.fileButton, SIGNAL('clicked()'), self.startConversion)
			self.ui.tabWidget.setCurrentIndex(1)
			self.header_pointer = int(self.entrada.read(15))
			self.entrada.seek(self.header_pointer, os.SEEK_SET)
			self.header = pickle.load(self.entrada)
			self.entrada.seek(15, os.SEEK_SET)
			self.salida.write('0'*15)
			self.endReached = False
			self.timer = QTimer()
			self.timer.start(1)
			self.index = list()
			self.connect(self.timer, SIGNAL('timeout()'), self.timeout)
		except:
			traceback.print_exc()
			if self.entrada != None: self.entrada.close()
			if self.salida != None: self.salida.close()
#
# Timeout
	def timeout(self):
		if not self.endReached:
			if self.header_pointer > self.entrada.tell():
				try:
					self.ret = pickle.load(self.entrada)
					self.measures+=1
					if self.writtenMeasures <= self.ret.time*self.mps/1000 or self.writtenMeasures == 0:
						salidaTell = self.salida.tell()
						pickle.dump(self.ret, self.salida, 2)
						self.index.append(salidaTell)
						self.writtenMeasures += 1
					self.ui.progressBar.setValue((self.measures*99.9)/len(self.header.index))
				except EOFError:
					print "Nos hemos pasado leyendo"
					self.endReached = True
				except:
					print "Algun otro error"
					self.endReached = True
			else:
				self.endReached = True
		else:
			self.header.index = self.index
			self.header_pointer = self.salida.tell()
			pickle.dump(self.header, self.salida, 2)
			self.salida.seek(0, os.SEEK_SET)
			self.salida.write(str(self.header_pointer).zfill(15))
			self.timer.stop()
			self.salida.close()
			print 'done'
			for i in range(3):
				self.ui.tabWidget.setTabEnabled(i, False)
			self.ui.tabWidget.setTabEnabled(2, True)
			self.ui.tabWidget.setCurrentIndex(2)
			
#
# Close event
	def closeEvent(self, e):
		pass
		#e.ignore()


############################
##   G U I    C L A S S   ##
############################
class ReplayMDISubwindow(QMdiSubWindow):
	def __init__(self):
		QMdiSubWindow.__init__(self)
	def closeEvent(self, e):
		e.ignore()
class ReplayCompUI(QMainWindow):
#
# Constructor
	def __init__(self):
		# Create Ice thread and synch
		self.ice = ReplayCompIce()		  
		self.ice.start()
		self.paused = False
		icerunning = False
		self.finishing = False
		while icerunning == False:
			try:
				while self.ice.running == False: time.sleep(0.05)
				icerunning = True
			except:
				time.sleep(0.05)
		self.mode = self.ice.mode
		self.measures = 0
		# GUI stuff
		QMainWindow.__init__(self)
		self.ui = Ui_ReplayMainWindow()
		self.ui.setupUi(self)
		self.ui.slider.setRange(0, len(self.ice.header.index)-1)
		self.ui_ticks = 0
		self.connect(self.ui.actionTile, SIGNAL('triggered(bool)'), self.tile)
		self.connect(self.ui.actionCascade, SIGNAL('triggered(bool)'), self.cascade)
		# Add plug-in windows to the MDI area
		global debug
		if debug: print 'Header list'
		for cfgId in self.ice.header.cfgDict:
			if debug: print cfgId
			cfg = self.ice.header.cfgDict[cfgId]
			cfg.gui_class = cfg.module.getGraphicalUserInterface()
			cfg.gui_class.setConfiguration(cfg.configuration)
			if cfg.gui_class == None: cfg.gui_class = DummyWidget(cfgId+' didn\'t returned a GUI')
			cfg.gui_class.show()
			self.ice.header.cfgDict[cfgId] = cfg
			subwin = ReplayMDISubwindow()
			subwin.setWidget(cfg.gui_class)
			window = self.ui.mdiArea.addSubWindow(subwin)
			window.setWindowTitle(cfgId)
			try:
				window.resize(cfg.gui_class.getSize())
			except:
				window.resize(400, 400)
		# Mode dependent UI config
		if self.mode == 'capture':
			self.ui.label.setEnabled(False)
			self.ui.PPButton.setEnabled(False)
			self.ui.forceButton.setEnabled(False)
			self.ui.spinBox.setEnabled(False)
			self.ui.slider.setEnabled(False)
			self.ui.statusbar.showMessage('Running in \'capture\' mode, controls are disabled.')
		else:
			self.ui.statusbar.showMessage('Running in \'replay\' mode.')
			self.tray = QSystemTrayIcon()
			self.connect(self.tray, SIGNAL('activated(QSystemTrayIcon::ActivationReason)'), self.trayClicked)
			self.iconGreen = QIcon("/opt/robocomp/icons/replay-green-icon.png")
			self.iconRed = QIcon("/opt/robocomp/icons/replay-red-icon.png")
			self.tray.setIcon(self.iconGreen)
			self.tray.show()
			self.menu = QMenu()
			self.ppaction = self.menu.addAction("Pause")
			self.connect(self.ppaction, SIGNAL('triggered(bool)'), self.playpause);
			self.connect(self.menu.addAction("Exit"), SIGNAL('triggered(bool)'), self.closeEvent);
			self.tray.setContextMenu(self.menu);
		# Signal handling
		self.timer = QTimer()
		if self.mode == 'capture': self.timer.start(200)
		else: self.changeSpeed(1.)
		self.connect(self.timer, SIGNAL('timeout()'), self.timeout)
		self.connect(self.ui.spinBox, SIGNAL('valueChanged(double)'), self.changeSpeed)
		self.connect(self.ui.PPButton, SIGNAL('clicked()'), self.playpause)
		self.connect(self.ui.forceButton, SIGNAL('clicked()'), self.force)
#
# TrayClicked
	def trayClicked(self, reason):
		if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.MiddleClick:
			if self.isHidden():
				self.show()
			else:
				self.hide()
#
# Timeout
	def timeout(self, force=False):
		if self.finishing:
			self.finish()
			return
		do_gui_update = True
		# Timeout - CAPTURE
		if self.mode == 'capture':
			self.ice.writeMeasureSet()
			if do_gui_update:
				for cfg in self.ice.header.cfgDict.values():
					cfg.gui_class.setMeasure(cfg.worker_class.getMeasure())
		# Timeout - READ
		elif self.mode == 'replay' and ((not self.paused) or force):
			if self.ice.readMeasureSet(force) == True:
				self.disconnect(self.ui.slider, SIGNAL('sliderMoved(int)'), self.changeTime)
				self.ui.slider.setSliderPosition(self.ice.reader.measures)
				self.connect(self.ui.slider, SIGNAL('sliderMoved(int)'), self.changeTime)
				#if not self.ui_ticks % 30/self.period == 0: do_gui_update = False
				if do_gui_update:
					for cfg in self.ice.header.cfgDict.values():
						cfg.gui_class.setMeasure(cfg.worker_class.getMeasure())
		# UI update
		if do_gui_update:
			for cfg in self.ice.header.cfgDict.values():
				cfg.gui_class.update()
		self.measures += 1
		self.ui_ticks += 1
#
# Handle quit
	def finish(self):
		self.disconnect(self.timer, SIGNAL('timeout()'), self.timeout)
		self.ice.done()
		self.close()
		if self.mode == 'capture':
			self.exitMessage.close()
		sys.exit(0)
#
# Handle speed-up value changes
	def changeSpeed(self, newSpeed):
		self.ice.setSpeedUp(newSpeed)
		self.period = int(round(30./newSpeed))
		self.timer.start(self.period)
#
# Handle jumps in time
	def changeTime(self, newIdx):
		self.ice.goto(newIdx)
#
# Play/Pause
	def playpause(self):
		if self.paused:
			self.paused = False
			self.ui.PPButton.setText('Pause')
			self.ppaction.setText('Pause')
			self.ui.forceButton.setEnabled(False)
			self.tray.setIcon(self.iconGreen)
		else:
			self.paused = True
			self.ui.PPButton.setText('Continue')
			self.ppaction.setText('Continue')
			self.ui.forceButton.setEnabled(True)
			self.tray.setIcon(self.iconRed)
#
# Force next measure
	def force(self):
		self.timeout(force=True)
#
# Close event
	def closeEvent(self, e):
		if self.mode == 'capture':
			self.exitMessage = ReplayExitMessage('Please wait while file header\nheader is written to file.', self)
			self.exitMessage.start()
		self.finishing = True
		e.ignore()
	def tile(self, b):
		self.ui.mdiArea.tileSubWindows()
	def cascade(self, b):
		self.ui.mdiArea.cascadeSubWindows()



if __name__ == '__main__':
	app = QApplication(argv)
	ice = None
	if (sys.argv[-1] == "--frameskip"):
		mainclass = ReplayFrameskipUI()
		mainclass.show()
	else:
		clase = ReplayCompUI()
		clase.show()
	app.exec_()

