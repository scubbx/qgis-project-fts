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
from qgis.PyQt.QtWidgets import QAction, QListWidgetItem
from qgis.core import QgsMessageLog
from qgis.core import Qgis
from qgis.core import QgsProject
from qgis.core import QgsTask
from qgis.core import QgsApplication
from qgis.core import QgsVectorLayer
from qgis.core import QgsGeometry
from qgis.core import QgsCoordinateReferenceSystem
from qgis.core import QgsCoordinateTransform
import qgis

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the DockWidget
from .project_fts_dockwidget import projectFTSDockWidget
from pathlib import Path
import os.path
import os
import shutil

import sqlite3
import copy
import math
import tempfile

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
        self.layersAdded_signal = QgsProject.instance().layersAdded.connect(self.add_layers)
        self.layersRemoved_signal = QgsProject.instance().layersRemoved.connect(self.remove_layers)

        self.set_db_path()
        self.tasklist = []

        self.sqlite_isolation_level = "IMMEDIATE" # possible values: DEFERRED, IMMEDIATE, EXCLUSIVE

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

        QgsProject.instance().layersAdded.disconnect(self.layersAdded_signal)
        QgsProject.instance().layersRemoved.disconnect(self.layersRemoved_signal)

    #--------------------------------------------------------------------------

    def completed(self, exception, result=None):
        """This is called when insert_features is finished.
        Exception is not None if insert_features raises an exception.db_path
        result is the return value of insert_features."""
        QgsMessageLog.logMessage(f"completed(): {exception}", tag="ftsPlugin", level=Qgis.Info)
        self.refresh_info()
        if exception is None:
            if result is None:
                QgsMessageLog.logMessage(
                    'Completed with no exception and no result '\
                    '(probably manually canceled by the user)',
                    tag="ftsPlugin", level=Qgis.Critical)
            else:
                QgsMessageLog.logMessage(
                    'Task {name} completed\n'
                    'Total: {total} ( with {iterations} '
                    'iterations)'.format(
                        name=result['task'],
                        total=result['total'],
                        iterations=result['iterations']),
                    tag="ftsPlugin", level=Qgis.Info)
        else:
            QgsMessageLog.logMessage("Exception: {}".format(exception), tag="ftsPlugin", level=Qgis.Critical)
            raise exception

    def refresh_info(self):
        QgsMessageLog.logMessage(f"refresh_info()", tag="ftsPlugin", level=Qgis.Info)
        ## how many layers are indexed
        info_num_layers = len(self.list_index_files(self.db_path))
        info_dirsize = sum(f.stat().st_size for f in Path(self.db_path).glob('**/*') if f.is_file())
        self.dockwidget.labelDBInfo.setText(f"search databases: {info_num_layers} ({int(info_dirsize/1024**2)} MB)")

    def add_layers(self, layers):
        # Create sqlite db on first added layer
        for layer_num, layer in enumerate(layers):
            ## build list of attributes
            #feature_attributes = []
            #for feature in layer.getFeatures():
            #    feature_attributes.append([ str(x) for x in feature.attributes() ])

            index_file_path = os.path.join(self.db_path,f"{layer.id()}.fts",)
            if not os.path.exists(index_file_path):
                # Store layer attributes in sqlite table
                layer_uri = layer.dataProvider().dataSourceUri()
                #layer_id = layer.id()
                #self.create_index_file(index_file_path)
                try:
                    total_steps = layer.featureCount()
                except AttributeError as err:
                    QgsMessageLog.logMessage(f"{err}", tag="ftsPlugin", level=Qgis.Warning)
                    continue
                
                QgsMessageLog.logMessage(f"Indexing Layer '{layer.name()}' ({layer_num+1}/{len(layers)}) ...", tag="ftsPlugin", level=Qgis.Info)

                task = QgsTask.fromFunction(f"Indexing Layer '{layer.name()}' ({layer_num+1}/{len(layers)})",
                                            self.insert_features,
                                            on_finished=self.completed,
                                            db_path=copy.copy(self.db_path),
                                            total_steps=copy.copy(total_steps),
                                            layer_id=copy.copy(layer.id()),
                                            index_file_path=index_file_path)
                # IMPORTANT! We have to explicitly make the task visible to pythons garbage collector to
                # make sure delayed tasks are not removed while they are waiting for execution by
                # the C++ code of QGIS.
                self.tasklist.append(task)
                QgsApplication.taskManager().addTask(task)

            # Connect to layer attribute value changed signal
            layer.attributeValueChanged.connect(self.update_feature)

    def remove_layers(self, layer_ids):
        # todo: layers does seem to contain the layername+hash which is not found by .mapLayersByName()
        QgsMessageLog.logMessage(f"remove_layers()", tag="ftsPlugin", level=Qgis.Info)
        QgsMessageLog.logMessage(f"layer_ids: {layer_ids}", tag="ftsPlugin", level=Qgis.Info)

        for layer_id in layer_ids:
            QgsMessageLog.logMessage(f"layer_id: {layer_id}", tag="ftsPlugin", level=Qgis.Info)
            # Remove table for this layer
            #project_layer = QgsProject.instance().mapLayer(layer_id)
            #layer_uri = project_layer.dataProvider().dataSourceUri()
            #QgsMessageLog.logMessage(f"layer_uri: {layer_uri}", tag="ftsPlugin", level=Qgis.Info)

            self.drop_index_file(layer_id)
        self.refresh_info()

    def list_index_files(self, index_folder):
        index_files = [x.name for x in os.scandir(index_folder) if x.is_file() and x.name.endswith(".fts")]
        return index_files

    def set_db_path(self):
        # create or load a database
        QgsMessageLog.logMessage(f"set_db_path()", tag="ftsPlugin", level=Qgis.Info)
        if self.db_path is None:
            if QgsProject.instance().fileName() != "":
                QgsMessageLog.logMessage(f"creating fts database at {QgsProject.instance().fileName()}.fts", tag="ftsPlugin", level=Qgis.Info)
                self.db_path = f"{QgsProject.instance().fileName()}.fts"
            else:
                QgsMessageLog.logMessage(f"Project is not saved yet, creating fts database at '{tempfile.gettempdir()}/qgisfts'", tag="ftsPlugin", level=Qgis.Info)
                self.db_path = os.path.join(tempfile.gettempdir(),'qgis.fts')
        else:
            pass
        os.makedirs(self.db_path, exist_ok=True)

    def insert_features(self, task: QgsTask, db_path, total_steps, layer_id, index_file_path):
        QgsMessageLog.logMessage(f"(insert_feature): {layer_id}", tag="ftsPlugin", level=Qgis.Info)
        project_layer = QgsProject.instance().mapLayer(layer_id)
        uri = project_layer.dataProvider().dataSourceUri()
        
        #raise Exception ("Hello")

        # load the layer with features to be imported
        layer = QgsVectorLayer(uri, "importlayer", "ogr")
        if not layer.isValid():
            # data souce is non-valid, so do not operate on it (might be an e.g. raster)
            task.setProgress(100)
            del(layer)
            task.exception = Exception("Layer is not valid")
            return False
        
        # set all actual qgis project layers to read-only during the indexing process
        project_layer.setReadOnly(True)
        
        # Insert layer features into corresponding sqlite table
        # we have to use an own connection and cursor object, since we cannot
        # use an element from the main-thread
        #conn = sqlite3.connect(index_file_path, timeout=10, isolation_level=self.sqlite_isolation_level)
        conn = sqlite3.connect(index_file_path, timeout=10)
        conn.isolation_level = None
        cur = conn.cursor()

        cur.execute("BEGIN")
        
        # create and fill the metadata table
        cur.execute("CREATE TABLE IF NOT EXISTS 'ftslayers' (layer_id)")
        cur.execute("INSERT INTO 'ftslayers' (layer_id) VALUES ( ? )", (layer_id,) )
        
        # create the actual data table
        cur.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS '{layer_id}' USING fts5 (fid, data, centerwkt,  tokenize='trigram')" )

        cur.execute("COMMIT")

        # prepare the insert statement for the insert-loop
        sql = f"INSERT INTO '{layer_id}' (fid, data, centerwkt) VALUES (?, ?, ?)"
        
        all_features = layer.getFeatures()

        # prepare the transformation object to transform all layers geometries to EPSG:4326
        #source_crs = QgsCoordinateReferenceSystem(layer.crs())
        source_crs = layer.crs()
        dest_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        transformation = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())

        cur.execute("BEGIN")

        span_size = 10000
        allfeats = []
        for i, feature in enumerate(layer.getFeatures()):
            if feature.hasGeometry():
                # Fortschritt aktualisieren
                task.setProgress((i + 1) / total_steps * 100)
                feature_attributes = " ".join([ str(x) for x in feature.attributes() if str(x) != "NULL" ])
                transformedPoint = transformation.transform(feature.geometry().centroid().asPoint() ).asWkt()
                singleobject = (feature.id(),feature_attributes,transformedPoint)
                allfeats.append(singleobject)
                if len(allfeats) >= span_size:
                    cur.executemany(sql, allfeats )
                    allfeats = []
        
        if len(allfeats) > 0: cur.executemany(sql, allfeats )

        cur.execute("COMMIT")
        conn.commit()
        # Remove layer from memory
        del(layer)

        # remove read-only flag from layers matching the current layer-uri
        project_layer.setReadOnly(False)
        cur.close()
        conn.close()
        QgsMessageLog.logMessage(f"Committed change, connection is closed", tag="ftsPlugin", level=Qgis.Info)
        return True  # Task wurde erfolgreich abgeschlossen
        
    def update_feature(self, fid, idx, value):
        # Update sqlite table on attribute changes
        QgsMessageLog.logMessage(f"update_feature()", tag="ftsPlugin", level=Qgis.Info)
        pass

    def drop_index_file(self, layer_id):
        index_file_path = os.path.join(self.db_path,f"{layer_id}.fts")
        QgsMessageLog.logMessage(f"drop_index_file() with index file {index_file_path}", tag="ftsPlugin", level=Qgis.Info)
        if os.path.exists(index_file_path): os.remove(index_file_path)

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
            self.dockwidget.buttonClear.clicked.connect(self.clear_search_box)
            self.dockwidget.textSearch.textChanged.connect(self.search_fts)
            self.dockwidget.listView.itemClicked.connect(self.clicked_object)
            
            self.refresh_info()

            # perform a layer-add of all layers
            if len(QgsProject.instance().mapLayers().values()) > 0:
                self.add_layers(QgsProject.instance().mapLayers().values())

    def clear_search_box(self):
        self.dockwidget.textSearch.clear()
        self.dockwidget.textSearch.setFocus()

    def clicked_object(self):
        obj_index = self.dockwidget.listView.currentRow()
        obj = self.dockwidget.listView.item(obj_index)
        QgsMessageLog.logMessage(f"clicked '{obj.text()}'", tag="ftsPlugin", level=Qgis.Info)
        QgsMessageLog.logMessage(f"coords are: '{obj.data(Qt.UserRole)}'", tag="ftsPlugin", level=Qgis.Info)
        canvas = qgis.utils.iface.mapCanvas()

        source_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        dest_crs = QgsProject.instance().crs()
        transformation = QgsCoordinateTransform(source_crs, dest_crs, QgsProject.instance())

        point = transformation.transform(QgsGeometry.fromWkt(obj.data(Qt.UserRole)).asPoint())
        canvas.setCenter(point)
        canvas.refresh()
        #QgsMessageLog.logMessage(f"canvas size: {canvas.size()}", tag="ftsPlugin", level=Qgis.Info)


    def reload_all(self):
        QgsMessageLog.logMessage(f"reload_all()", tag="ftsPlugin", level=Qgis.Info)
        # if there are already layers active, perform a layer-add of all layers

        # first remove old database
        if self.db_path is not None: 
            if QgsProject.instance().fileName() is not None:
                if os.path.exists(self.db_path):
                    shutil.rmtree(self.db_path)
            else:
                if os.path.exists(os.path.join(tempfile.gettempdir(),'qgis.fts')):
                    os.remove(os.path.join(tempfile.gettempdir(),'qgis.fts'))
            self.db_path = None
        
        self.set_db_path()
        
        self.refresh_info()
        if len(QgsProject.instance().mapLayers().values()) > 0:
            self.add_layers(QgsProject.instance().mapLayers().values())

    def search_fts(self, searchtext):
        searchtext = searchtext.replace(","," ").replace(";"," ")
        self.dockwidget.listView.clear()
        if len(searchtext) > 3:
            QgsMessageLog.logMessage(f"search_fts in ({self.db_path})", tag="ftsPlugin", level=Qgis.Info)
            for index_file_name in self.list_index_files(self.db_path):
                layer_name = index_file_name.split(".")[0] # remove the ".fts" extension
                QgsMessageLog.logMessage(f"search_fts({index_file_name})", tag="ftsPlugin", level=Qgis.Info)
                conn = sqlite3.connect(os.path.join(self.db_path,index_file_name), timeout=10, isolation_level=self.sqlite_isolation_level)
                cur = conn.cursor()

                # fetch all available tables inside one database file
                indextables = cur.execute("SELECT layer_id FROM 'ftslayers'").fetchall()
                tablelist = [x[0] for x in list(indextables)]
                tablelist_string = ",".join(tablelist)
                #QgsMessageLog.logMessage(f"tablelist_string is: ({tablelist_string})", tag="ftsPlugin", level=Qgis.Info)

                searchresult = cur.execute(f"SELECT * FROM {tablelist_string} WHERE data MATCH ?", (searchtext,)).fetchall()
                for singleresult in searchresult:
                    #QgsMessageLog.logMessage(f"searchresults: {singleresult}", tag="ftsPlugin", level=Qgis.Info)
                    ftsstring = str(singleresult[1])
                    listitem = QListWidgetItem(ftsstring)
                    listitem.setData(Qt.UserRole, str(str(singleresult[2])))
                    self.dockwidget.listView.addItem(listitem)
                cur.close()
                conn.close()
#boundingwkt

#            sql = "SELECT layer_id FROM fts5qgis"
#            alltablescur = cur.execute(sql)
#            alltablesresults = alltablescur.fetchall()
#            for singletable in alltablesresults:
#                singletablename = singletable[0]
#                sql = f"SELECT * FROM '{singletablename}' WHERE data MATCH ?"
#                searchcursor = cur.execute(sql, (searchtext,))
#                searchresult = searchcursor.fetchall()
#                for singleresult in searchresult:
#                    self.dockwidget.listView.addItem(str(singleresult))
#            cur.close()
#            conn.close()
    