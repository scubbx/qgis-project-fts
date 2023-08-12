# -*- coding: utf-8 -*-
"""
/***************************************************************************
 projectFTS
                                 A QGIS plugin
 This plugin generates a full text search index containing all attributes of all layers of a loaded project. The user then can use a single text-input field to search within all available attributes.
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-07-14
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Markus Mayr
        email                : markus.mayr@gisforge.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsMessageLog
from qgis.core import Qgis
from qgis.core import QgsProject
from qgis.core import QgsTask
from qgis.core import QgsApplication
from qgis.core import QgsVectorLayer
from qgis.core import QgsFeatureRequest

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .project_fts_dockwidget import projectFTSDockWidget
import os.path
import os

import sqlite3
import copy

class projectFTS:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'projectFTS_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Project Full Text Search')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'projectFTS')
        self.toolbar.setObjectName(u'projectFTS')

        #print "** INITIALIZING projectFTS"

        self.pluginIsActive = False
        self.dockwidget = None

        self.db_path = None
        self.conn = None
        self.cur = None


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('projectFTS', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action


    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/project_fts/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Full Text Search'),
            callback=self.run,
            parent=self.iface.mainWindow())
        
        QgsProject.instance().layersAdded.connect(self.add_layers)
        QgsProject.instance().layersRemoved.connect(self.remove_layers)

    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        #print "** CLOSING projectFTS"

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None
        self.cur.close()
        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        #print "** UNLOAD projectFTS"

        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Project Full Text Search'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar

    #--------------------------------------------------------------------------

    def table_exists(self, table_name):
        cur = self.conn.cursor()
        sql = "SELECT * FROM sqlite_master WHERE type='table' AND tbl_name=?"
        searchcursor = cur.execute(sql, (table_name,))
        searchresult = searchcursor.fetchall()
        cur.close()
        if len(searchresult) > 0:
            QgsMessageLog.logMessage(f"Layer '{table_name}' already exists in the fts database", tag="ftsPlugin", level=Qgis.Info)
            return True
        else:
            QgsMessageLog.logMessage(f"Layer '{table_name}' does not exist in the fts database", tag="ftsPlugin", level=Qgis.Info)
            return False

    def completed(self, exception, result=None):
        """This is called when doSomething is finished.
        Exception is not None if doSomething raises an exception.
        result is the return value of insert_features."""
        QgsMessageLog.logMessage("completed()", tags="ftsPlugin", level=Qgis.Info)
        self.refresh_info()
        if exception is None:
            if result is None:
                QgsMessageLog.logMessage(
                    'Completed with no exception and no result '\
                    '(probably manually canceled by the user)',
                    tags="ftsPlugin", level=Qgis.Critical)
            else:
                QgsMessageLog.logMessage(
                    'Task {name} completed\n'
                    'Total: {total} ( with {iterations} '
                    'iterations)'.format(
                        name=result['task'],
                        total=result['total'],
                        iterations=result['iterations']),
                    tags="ftsPlugin", level=Qgis.Info)
        else:
            QgsMessageLog.logMessage("Exception: {}".format(exception), tags="ftsPlugin", level=Qgis.Critical)
            raise exception

    def refresh_info(self):
        # how many layers are indexed
        sql = "select layer_uri from fts5qgis from fts5qgis"
        sql_result = self.cur.execute(sql)
        info_num_layers = len(sql_result.fetchall())

        self.dockwidget.labelDBInfo.text = f"layers loaded: {info_num_layers}"


    def add_layers(self, layers):
        for layer_num, layer in enumerate(layers):
            # Create sqlite db on first added layer
            self.set_db()
            
            ## build list of attributes
            #feature_attributes = []
            #for feature in layer.getFeatures():
            #    feature_attributes.append([ str(x) for x in feature.attributes() ])

            if not self.table_exists(layer.dataProvider().dataSourceUri()):
                # Store layer attributes in sqlite table
                layer_name = layer.name()
                uri = layer.dataProvider().dataSourceUri()
                self.create_table(uri)
                total_steps = layer.featureCount()
                QgsMessageLog.logMessage(f"Indexing Layer {layer_num+1}/{len(layers)} ...", tag="ftsPlugin", level=Qgis.Info)
                task = QgsTask.fromFunction(f"Indexing Layer {layer_num+1}/{len(layers)}",
                                            self.insert_features,
                                            on_finished=self.completed,
                                            db_path=self.db_path,
                                            total_steps=copy.copy(total_steps),
#                                            all_features=feature_attributes,
                                            layer_name=layer_name,
                                            uri=uri)
                QgsApplication.taskManager().addTask(task)

            # Connect to layer attribute value changed signal
            layer.attributeValueChanged.connect(self.update_feature)

    def remove_layers(self, layers):
        QgsMessageLog.logMessage(f"remove_layers()", tag="ftsPlugin", level=Qgis.Info)
        for layer in layers:
            # Remove table for this layer
            layer_name = layer
            self.drop_table(layer_name)

    def set_db(self):
        # create or load a database
        QgsMessageLog.logMessage(f"create_db()", tag="ftsPlugin", level=Qgis.Info)
        if self.db_path is None: 
            QgsMessageLog.logMessage(f"Project Filename is '{QgsProject.instance().fileName()}'", tag="ftsPlugin", level=Qgis.Info)
            if QgsProject.instance().fileName() != "":
                QgsMessageLog.logMessage(f"creating fts database at {QgsProject.instance().fileName()}.fts.sqlite", tag="ftsPlugin", level=Qgis.Info)
                self.db_path = f"{QgsProject.instance().fileName()}.fts.sqlite"
                #self.db_path = f"/tmp/unsaved.fts.sqlite"
                self.conn = sqlite3.connect(self.db_path)
            else:
                QgsMessageLog.logMessage(f"creating fts database as in-memory database", tag="ftsPlugin", level=Qgis.Info)
                self.db_path = ':memory:'
                self.conn = sqlite3.connect(':memory:')
        self.cur = self.conn.cursor()

        # prepare metadata table
        sql = f"CREATE TABLE IF NOT EXISTS fts5qgis (id integer PRIMARY KEY, layer_uri text NOT NULL)"
        self.cur.execute(sql)
        self.conn.commit()

#        self.conn.close()

    def create_table(self, uri):
        # SQL for creating a table matching the layer schema
        #QgsMessageLog.logMessage(f"CREATE VIRTUAL TABLE IF NOT EXISTS {uri} USING fts5 (fid, data, uri, tokenize='trigram')", tag="ftsPlugin")
        sql = f"CREATE VIRTUAL TABLE IF NOT EXISTS '{uri}' USING fts5 (fid, data, tokenize='trigram')"
        self.cur.execute(sql)

        # insert data to metadata-table
        sql = "INSERT INTO fts5qgis (layer_uri) VALUES( ? )"
        self.cur.execute(sql, (uri,))
        self.conn.commit()

    def insert_features(self, task: QgsTask, db_path, total_steps, layer_name, uri):
        # select the actual layer of the qgis project
        project_layers = QgsProject.instance().mapLayersByName(layer_name)
        # set all actual qgis project layers to read-only during the indexing process
        for project_layer in project_layers:
            project_layer.setReadOnly(True)
        
        # load the layer with features to be imported
        layer = QgsVectorLayer(uri, layer_name, "ogr")
        if not layer.isValid():
            task.setProgress(100)
            layer.dataProvider().dataSourceUri().clear()
            return True
        
        QgsMessageLog.logMessage(f"Begin inserting features ({layer.featureCount()} in total)", tag="ftsPlugin", level=Qgis.Info)
        # Insert layer features into corresponding sqlite table
        # we have to use an own connection and cursor object, since we cannot
        # use an element from the main-thread
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        sql = f"INSERT INTO '{uri}' (fid, data) VALUES (?, ?)"

        #all_features = layer.getFeatures()

        #for i, feature in enumerate(layer.getFeatures()):
        for i, feature in enumerate(layer.getFeatures(QgsFeatureRequest().setFlags(QgsFeatureRequest.NoGeometry))):
            # Fortschritt aktualisieren
            task.setProgress((i + 1) / total_steps * 100)
            feature_id = feature.id()
            feature_attributes = ";".join([ str(x) for x in feature.attributes() ])
            cur.execute(sql, (feature_id , feature_attributes) )
            # Fortschritt aktualisieren und überprüfen, ob der Task abgebrochen wurde
            if task.isCanceled():
                return None  # Task wurde abgebrochen

        conn.commit()
        # Datei schließen, wenn sie nicht mehr benötigt wird
        layer.dataProvider().dataSourceUri().clear()
        return True  # Task wurde erfolgreich abgeschlossen
        
    def update_feature(self, fid, idx, value):
        # Update sqlite table on attribute changes
        QgsMessageLog.logMessage(f"update_feature()", tag="ftsPlugin", level=Qgis.Info)
        pass

    def drop_table(self, name):
        # SQL for dropping a table
        QgsMessageLog.logMessage(f"drop_table()", tag="ftsPlugin", level=Qgis.Info)
        pass

    def run(self):
        """Run method that loads and starts the plugin"""
        QgsMessageLog.logMessage(f"run()", tag="ftsPlugin", level=Qgis.Info)
        if not self.pluginIsActive:
            self.pluginIsActive = True

            #print "** STARTING projectFTS"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = projectFTSDockWidget()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

            QgsMessageLog.logMessage(f"QgsProject.fileName(): {QgsProject.instance().fileName()}", tag="ftsPlugin", level=Qgis.Info)
            QgsMessageLog.logMessage(f"QgsProject.fileInfo(): {QgsProject.instance().fileName()}", tag="ftsPlugin", level=Qgis.Info)

            self.dockwidget.buttonRefreshIndex.clicked.connect(self.reload_all)
            self.dockwidget.textSearch.textChanged.connect(self.search_fts)

            # perform a layer-add of all layers
            if len(QgsProject.instance().mapLayers().values()) > 0:
                self.add_layers(QgsProject.instance().mapLayers().values())

    def reload_all(self):
        QgsMessageLog.logMessage(f"reload_all()", tag="ftsPlugin", level=Qgis.Info)
        # if there are already layers active, perform a layer-add of all layers

        # first remove old database
        if self.db_path is not None: 
            if QgsProject.instance().fileName() is not None:
                if os.path.exists(f"{QgsProject.instance().fileName()}.fts.sqlite"):
                    os.remove(f"{QgsProject.instance().fileName()}.fts.sqlite")
            else:
                if os.path.exists("/tmp/unsaved.fts.sqlite"):
                    os.remove("/tmp/unsaved.fts.sqlite")
            self.db_path = None
        if len(QgsProject.instance().mapLayers().values()) > 0:
            self.add_layers(QgsProject.instance().mapLayers().values())

    def search_fts(self, searchtext):
        self.dockwidget.listView.clear()
        if len(searchtext) > 3:
            #QgsMessageLog.logMessage(f"search_fts({searchtext})", tag="ftsPlugin", level=Qgis.Info)
            self.cur = self.conn.cursor() 
            sql = "SELECT layer_uri FROM fts5qgis"
            alltablescur = self.cur.execute(sql)
            alltablesresults = alltablescur.fetchall()
            for singletable in alltablesresults:
                singletablename = singletable[0]
                sql = f"SELECT * FROM '{singletablename}' WHERE data MATCH ?"
                searchcursor = self.cur.execute(sql, (searchtext,))
                searchresult = searchcursor.fetchall()
                for singleresult in searchresult:
                    self.dockwidget.listView.addItem(str(singleresult))