# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'pvtabwidget.ui'
#
# Created: Mon Apr 23 13:15:29 2012
#      by: PyQt4 UI code generator 4.8.3
#
# WARNING! All changes made in this file will be lost!

from PyQt4 import QtCore, QtGui

try:
    _fromUtf8 = QtCore.QString.fromUtf8
except AttributeError:
    _fromUtf8 = lambda s: s

class Ui_PVTabWidget(object):
    def setupUi(self, PVTabWidget):
        PVTabWidget.setObjectName(_fromUtf8("PVTabWidget"))
        PVTabWidget.resize(548, 141)
        self.gridLayout = QtGui.QGridLayout(PVTabWidget)
        self.gridLayout.setObjectName(_fromUtf8("gridLayout"))
        self.label = QtGui.QLabel(PVTabWidget)
        self.label.setObjectName(_fromUtf8("label"))
        self.gridLayout.addWidget(self.label, 0, 0, 1, 1)
        self.pvSelectedFileLineEdit = QtGui.QLineEdit(PVTabWidget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.pvSelectedFileLineEdit.sizePolicy().hasHeightForWidth())
        self.pvSelectedFileLineEdit.setSizePolicy(sizePolicy)
        self.pvSelectedFileLineEdit.setMinimumSize(QtCore.QSize(400, 20))
        self.pvSelectedFileLineEdit.setObjectName(_fromUtf8("pvSelectedFileLineEdit"))
        self.gridLayout.addWidget(self.pvSelectedFileLineEdit, 0, 1, 1, 1)
        self.pvPickLocalFileButton = QtGui.QToolButton(PVTabWidget)
        icon = QtGui.QIcon()
        icon.addPixmap(QtGui.QPixmap(_fromUtf8(":/icons/16x16/browse")), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        self.pvPickLocalFileButton.setIcon(icon)
        self.pvPickLocalFileButton.setObjectName(_fromUtf8("pvPickLocalFileButton"))
        self.gridLayout.addWidget(self.pvPickLocalFileButton, 0, 2, 1, 1)
        self.lVar = QtGui.QLabel(PVTabWidget)
        self.lVar.setObjectName(_fromUtf8("lVar"))
        self.gridLayout.addWidget(self.lVar, 1, 0, 1, 1)
        self.cbVar = QtGui.QComboBox(PVTabWidget)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Expanding, QtGui.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.cbVar.sizePolicy().hasHeightForWidth())
        self.cbVar.setSizePolicy(sizePolicy)
        self.cbVar.setMinimumSize(QtCore.QSize(100, 20))
        self.cbVar.setObjectName(_fromUtf8("cbVar"))
        self.gridLayout.addWidget(self.cbVar, 1, 1, 1, 1)
        self.strideLabel = QtGui.QLabel(PVTabWidget)
        self.strideLabel.setObjectName(_fromUtf8("strideLabel"))
        self.gridLayout.addWidget(self.strideLabel, 2, 0, 1, 1)
        self.horizontalLayout = QtGui.QHBoxLayout()
        self.horizontalLayout.setObjectName(_fromUtf8("horizontalLayout"))
        self.strideLineEditX = QtGui.QLineEdit(PVTabWidget)
        self.strideLineEditX.setObjectName(_fromUtf8("strideLineEditX"))
        self.horizontalLayout.addWidget(self.strideLineEditX)
        self.strideLineEditZ = QtGui.QLineEdit(PVTabWidget)
        self.strideLineEditZ.setObjectName(_fromUtf8("strideLineEditZ"))
        self.horizontalLayout.addWidget(self.strideLineEditZ)
        self.strideLineEditY = QtGui.QLineEdit(PVTabWidget)
        self.strideLineEditY.setObjectName(_fromUtf8("strideLineEditY"))
        self.horizontalLayout.addWidget(self.strideLineEditY)
        self.gridLayout.addLayout(self.horizontalLayout, 2, 1, 1, 1)
        spacerItem = QtGui.QSpacerItem(20, 40, QtGui.QSizePolicy.Minimum, QtGui.QSizePolicy.Expanding)
        self.gridLayout.addItem(spacerItem, 3, 1, 1, 1)

        self.retranslateUi(PVTabWidget)
        QtCore.QMetaObject.connectSlotsByName(PVTabWidget)

    def retranslateUi(self, PVTabWidget):
        PVTabWidget.setWindowTitle(QtGui.QApplication.translate("PVTabWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.label.setText(QtGui.QApplication.translate("PVTabWidget", "File:", None, QtGui.QApplication.UnicodeUTF8))
        self.pvPickLocalFileButton.setText(QtGui.QApplication.translate("PVTabWidget", "...", None, QtGui.QApplication.UnicodeUTF8))
        self.lVar.setText(QtGui.QApplication.translate("PVTabWidget", "Variables:", None, QtGui.QApplication.UnicodeUTF8))
        self.strideLabel.setText(QtGui.QApplication.translate("PVTabWidget", "Stride", None, QtGui.QApplication.UnicodeUTF8))
        self.strideLineEditX.setText(QtGui.QApplication.translate("PVTabWidget", "1", None, QtGui.QApplication.UnicodeUTF8))
        self.strideLineEditZ.setText(QtGui.QApplication.translate("PVTabWidget", "1", None, QtGui.QApplication.UnicodeUTF8))
        self.strideLineEditY.setText(QtGui.QApplication.translate("PVTabWidget", "1", None, QtGui.QApplication.UnicodeUTF8))

import pv_rc
import pv_rc
