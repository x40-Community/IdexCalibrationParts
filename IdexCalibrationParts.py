#-----------------------------------------------------------------------------------
# Part of the initial source code for primitive Shape (c) 2018 fieldOfView and CalibrationShapes (c) 2020-2022 5@xes
#
# The Idex Calibration Parts plugin is released under the terms of the AGPLv3 or higher.
# Modifications M4L 2023
#-----------------------------------------------------------------------------------
#
# V1.2.0
#-------------------------------------------------------------------------------------------
#
# - integrate select all and merge

VERSION_QT5 = False
try:
    from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot, QUrl
    from PyQt6.QtGui import QDesktopServices
except ImportError:
    from PyQt5.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot, QUrl
    from PyQt5.QtGui import QDesktopServices
    VERSION_QT5 = True

   
# Imports from the python standard library to build the plugin functionality
import os
import sys
import re
import math
import numpy
import trimesh
import shutil

from shutil import copyfile

from typing import Optional, List

from UM.Extension import Extension
from UM.PluginRegistry import PluginRegistry
from UM.Application import Application
from cura.CuraApplication import CuraApplication

from UM.Mesh.MeshData import MeshData, calculateNormalsFromIndexedVertices
from UM.Resources import Resources
from UM.Settings.SettingInstance import SettingInstance
from cura.Scene.CuraSceneNode import CuraSceneNode
from UM.Scene.SceneNode import SceneNode
from UM.Scene.Selection import Selection
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
from UM.Operations.SetTransformOperation import SetTransformOperation

from cura.CuraVersion import CuraVersion  # type: ignore
from UM.Version import Version

from UM.Logger import Logger
from UM.Message import Message

from UM.i18n import i18nCatalog

i18n_cura_catalog = i18nCatalog("cura")
i18n_catalog = i18nCatalog("fdmprinter.def.json")
i18n_extrud_catalog = i18nCatalog("fdmextruder.def.json")

Resources.addSearchPath(
    os.path.join(os.path.abspath(os.path.dirname(__file__)))
)  # Plugin translation file import

catalog = i18nCatalog("idexcalibration")

if catalog.hasTranslationLoaded():
    Logger.log("i", "Idex Calibration Parts Plugin translation loaded!")

#This class is the extension and doubles as QObject to manage the qml    
class IdexCalibrationParts(QObject, Extension):
    #Create an api
    from cura.CuraApplication import CuraApplication
    api = CuraApplication.getInstance().getCuraAPI()
    
    
    def __init__(self, parent = None) -> None:
        QObject.__init__(self, parent)
        
        self._calc_folder = "calculation"
        self._calc_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self._calc_folder, "Calulation_Tool.xls")
        
        self._controller = CuraApplication.getInstance().getController()
        self._message = None
        
        
        self.setMenuName(catalog.i18nc("@item:inmenu", "Add Part for IDEX Offset Calibration or Test"))
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Coarse Offset Calibration Part, like Weedo (1mm)"), self.addCoarsetuning)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Fine Offset Calibration Part, like Weedo (0.1mm)"), self.addFinetuning)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Alternativ Offset Calibration Part"), self.addExtruderOffsetCalibration)  
        self.addMenuItem("  ", lambda: None)  
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Flowtest cube"), self.addCube)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "2x2 Chessboard Pattern Part"), self.add2x2Chesspattern)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "3x3 Chessboard Pattern Part"), self.add3x3Chesspattern)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Manual and calculation tool"), self.gotoCalulation)
        self.addMenuItem("   ", lambda: None)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Bi-color Testcube"), self.addCubeBiColor)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "XYZ bi-Color Calibration Cube"), self.addHollowCalibrationCube)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Extruder change-over Testcube"), self.addExtruderChangeCube)
        self.addMenuItem("    ", lambda: None)
        self.addMenuItem(catalog.i18nc("@item:inmenu", "Help"), self.gotoHelp)
  

     
    def gotoHelp(self) -> None:
        QDesktopServices.openUrl(QUrl("http://www.x40-community.org/index.php/9-cura-workflow/89-cura-idex-calibration-parts-plugin"))

    def gotoCalulation(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._calc_path))
            
    def _registerShapeStl(self, mesh_name, mesh_filename=None, **kwargs) -> None:
        if mesh_filename is None:
            mesh_filename = mesh_name + ".stl"
        
        model_definition_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", mesh_filename)
        mesh =  trimesh.load(model_definition_path)
        
        fl=kwargs.get('flow', 0)
            
        # addShape
        if fl>0 :
            fact=kwargs.get('factor', 1)
            
            origin = [0, 0, 0]
            DirX = [1, 0, 0]
            DirY = [0, 1, 0]
            DirZ = [0, 0, 1]
            mesh.apply_transform(trimesh.transformations.scale_matrix(fact, origin, DirX))
            mesh.apply_transform(trimesh.transformations.scale_matrix(fact, origin, DirY))
            mesh.apply_transform(trimesh.transformations.scale_matrix(fact, origin, DirZ))
            mesh.apply_transform(trimesh.transformations.translation_matrix([0, (100-fl)*12*fact, 0]))
            self._addShapeFlow(mesh_name,self._toMeshData(mesh), **kwargs)
            
        else :
            self._addShape(mesh_name,self._toMeshData(mesh), **kwargs)
 
    # Source code from MeshTools Plugin 
    # Copyright (c) 2020 Aldo Hoeben / fieldOfView
    def _getAllSelectedNodes(self) -> List[SceneNode]:
        selection = Selection.getAllSelectedObjects()[:]
        if selection:
            deep_selection = []  # type: List[SceneNode]
            for selected_node in selection:
                if selected_node.hasChildren():
                    deep_selection = deep_selection + selected_node.getAllChildren()
                if selected_node.getMeshData() != None:
                    deep_selection.append(selected_node)
            if deep_selection:
                return deep_selection

        Message(catalog.i18nc("@info:status", "Please select one or more models first"))

        return []
 
    def _sliceableNodes(self):
        # Add all sliceable scene nodes to check
        scene = Application.getInstance().getController().getScene()
        for node in DepthFirstIterator(scene.getRoot()):
            if node.callDecoration("isSliceable"):
                yield node
                       
 
 
    #-----------------------------
    #   Dual Extruder Calibration parts  
    #-----------------------------    
    def addCoarsetuning(self) -> None:
        self._registerShapeStl("CoarseExt1", "coarse_tuning_part1.stl", ext_pos=1)
        self._registerShapeStl("CoarseExt2", "coarse_tuning_part2.stl", ext_pos=2)
        coarse = CuraApplication.getInstance()
        coarse.selectAll()
        coarse.mergeSelected()
        
    def addFinetuning(self) -> None:
        self._registerShapeStl("FineExt1", "fine_tuning_part1.stl", ext_pos=1)
        self._registerShapeStl("FineExt2", "fine_tuning_part2.stl", ext_pos=2)
        fine = CuraApplication.getInstance()
        fine.selectAll()
        fine.mergeSelected()
 
    def addExtruderOffsetCalibration(self) -> None:
        self._registerShapeStl("CalibrationMultiExtruder1", "nozzle-to-nozzle-xy-offset-calibration-pattern-a.stl", ext_pos=1)
        self._registerShapeStl("CalibrationMultiExtruder1", "nozzle-to-nozzle-xy-offset-calibration-pattern-b.stl", ext_pos=2)
        multi = CuraApplication.getInstance()
        multi.selectAll()
        multi.mergeSelected()

    def addCube(self) -> None:
        self._registerShapeStl("Flowtestcube", "cube_20x20x20.stl", ext_pos=1)
        self._application.getMachineManager().setExtruderEnabled(1, True)
 
    def  add2x2Chesspattern(self) -> None:
        self._registerShapeStl("2x2ChessExt1", "xy_calibration_2x2_part1.stl", ext_pos=1)
        self._registerShapeStl("2x2ChessExt2", "xy_calibration_2x2_part2.stl", ext_pos=2)
        chess2x2 = CuraApplication.getInstance()
        chess2x2.selectAll()
        chess2x2.mergeSelected()
        
    def  add3x3Chesspattern(self) -> None:
        self._registerShapeStl("3x3ChessExt1", "xy_calibration_3x3_part1.stl", ext_pos=1)
        self._registerShapeStl("3x3ChessExt2", "xy_calibration_3x3_part2.stl", ext_pos=2) 
        chess3x3 = CuraApplication.getInstance()
        chess3x3.selectAll()
        chess3x3.mergeSelected()
 
    #-----------------------------
    #   Dual Extruder Test parts
    #----------------------------- 
    def addCubeBiColor(self) -> None:
        self._registerShapeStl("CubeBiColorExt1", "40mm_two_color_cube_part1.stl", ext_pos=1)
        self._registerShapeStl("CubeBiColorExt2", "40mm_two_color_cube_part2.stl", ext_pos=2)
        bicolorcube = CuraApplication.getInstance()
        bicolorcube.selectAll()
        bicolorcube.mergeSelected()

    def addHollowCalibrationCube(self) -> None:
        self._registerShapeStl("CubeBiColorExt", "dual_color_xyz_cube_part1.stl", ext_pos=1)
        self._registerShapeStl("CubeBiColorInt", "dual_color_xyz_cube_part2.stl", ext_pos=2)
        calibrationcube = CuraApplication.getInstance()
        calibrationcube.selectAll()
        calibrationcube.mergeSelected()
       
    def addExtruderChangeCube(self) -> None:
        self._registerShapeStl("ChangeOverExt1", "change-over_testcube_part1.stl", ext_pos=1)
        self._registerShapeStl("ChangeOverExt2", "change-over_testcube_part2.stl", ext_pos=2)
        changeover = CuraApplication.getInstance()
        changeover.selectAll()
        changeover.mergeSelected()
        
        
    #----------------------------------------
    # Initial Source code from  fieldOfView
    #----------------------------------------  
    def _toMeshData(self, tri_node: trimesh.base.Trimesh) -> MeshData:
        # Rotate the part to laydown on the build plate
        # Modification from 5@xes
        tri_node.apply_transform(trimesh.transformations.rotation_matrix(math.radians(90), [-1, 0, 0]))
        tri_faces = tri_node.faces
        tri_vertices = tri_node.vertices

        # Following Source code from  fieldOfView
        # https://github.com/fieldOfView/Cura-SimpleShapes/blob/bac9133a2ddfbf1ca6a3c27aca1cfdd26e847221/SimpleShapes.py#L45
        indices = []
        vertices = []

        index_count = 0
        face_count = 0
        for tri_face in tri_faces:
            face = []
            for tri_index in tri_face:
                vertices.append(tri_vertices[tri_index])
                face.append(index_count)
                index_count += 1
            indices.append(face)
            face_count += 1

        vertices = numpy.asarray(vertices, dtype=numpy.float32)
        indices = numpy.asarray(indices, dtype=numpy.int32)
        normals = calculateNormalsFromIndexedVertices(vertices, indices, face_count)

        mesh_data = MeshData(vertices=vertices, indices=indices, normals=normals)

        return mesh_data        
        
    # Initial Source code from  fieldOfView
    # https://github.com/fieldOfView/Cura-SimpleShapes/blob/bac9133a2ddfbf1ca6a3c27aca1cfdd26e847221/SimpleShapes.py#L70
    def _addShape(self, mesh_name, mesh_data: MeshData, ext_pos = 0 , hole = False , thin = False ) -> None:
        application = CuraApplication.getInstance()
        global_stack = application.getGlobalContainerStack()
        if not global_stack:
            return

        node = CuraSceneNode()

        node.setMeshData(mesh_data)
        node.setSelectable(True)
        if len(mesh_name)==0:
            node.setName("TestPart" + str(id(mesh_data)))
        else:
            node.setName(str(mesh_name))

        scene = self._controller.getScene()
        op = AddSceneNodeOperation(node, scene.getRoot())
        op.push()

        extruder_stack = application.getExtruderManager().getActiveExtruderStacks() 
        
        extruder_nr=len(extruder_stack)
        # Logger.log("d", "extruder_nr= %d", extruder_nr)
        # default_extruder_position  : <class 'str'>
        if ext_pos>0 and ext_pos<=extruder_nr :
            default_extruder_position = int(ext_pos-1)
        else :
            default_extruder_position = int(application.getMachineManager().defaultExtruderPosition)
        # Logger.log("d", "default_extruder_position= %s", type(default_extruder_position))
        default_extruder_id = extruder_stack[default_extruder_position].getId()
        # Logger.log("d", "default_extruder_id= %s", default_extruder_id)
        node.callDecoration("setActiveExtruder", default_extruder_id)
 
        stack = node.callDecoration("getStack") # created by SettingOverrideDecorator that is automatically added to CuraSceneNode
        settings = stack.getTop()
        # Remove All Holes
        if hole :
            definition = stack.getSettingDefinition("meshfix_union_all_remove_holes")
            new_instance = SettingInstance(definition, settings)
            new_instance.setProperty("value", True)
            new_instance.resetState()  # Ensure that the state is not seen as a user state.
            settings.addInstance(new_instance) 
        # Print Thin Walls    
        if thin :
            definition = stack.getSettingDefinition("fill_outline_gaps")
            new_instance = SettingInstance(definition, settings)
            new_instance.setProperty("value", True)
            new_instance.resetState()  # Ensure that the state is not seen as a user state.
            settings.addInstance(new_instance)
 
            
        active_build_plate = application.getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))

        node.addDecorator(SliceableObjectDecorator())

        application.getController().getScene().sceneChanged.emit(node)
        
    def _addShapeFlow(self, mesh_name, mesh_data: MeshData, flow = 100 , factor = 1 , hole = False , thin = False ) -> None:
        application = CuraApplication.getInstance()
        global_stack = application.getGlobalContainerStack()
        if not global_stack:
            return

        node = CuraSceneNode()

        node.setMeshData(mesh_data)
        node.setSelectable(True)
        if len(mesh_name)==0:
            node.setName("TestPart" + str(id(mesh_data)))
        else:
            node.setName(str(mesh_name))

        scene = self._controller.getScene()
        op = AddSceneNodeOperation(node, scene.getRoot())
        op.push()
        
        extruder_stack = application.getExtruderManager().getActiveExtruderStacks() 

        extruder_nr=len(extruder_stack)
        # Logger.log("d", "extruder_nr= %d", extruder_nr)
        default_extruder_position = int(application.getMachineManager().defaultExtruderPosition)
        # Logger.log("d", "default_extruder_position= %s", type(default_extruder_position))
        default_extruder_id = extruder_stack[default_extruder_position].getId()
        # Logger.log("d", "default_extruder_id= %s", default_extruder_id)
        node.callDecoration("setActiveExtruder", default_extruder_id)

        stack = node.callDecoration("getStack") # created by SettingOverrideDecorator that is automatically added to CuraSceneNode
        settings = stack.getTop()
        # Remove All Holes
        if hole :
            definition = stack.getSettingDefinition("meshfix_union_all_remove_holes")
            new_instance = SettingInstance(definition, settings)
            new_instance.setProperty("value", True)
            new_instance.resetState()  # Ensure that the state is not seen as a user state.
            settings.addInstance(new_instance) 
        # Print Thin Walls
        if thin :
            definition = stack.getSettingDefinition("fill_outline_gaps")
            new_instance = SettingInstance(definition, settings)
            new_instance.setProperty("value", True)
            new_instance.resetState()  # Ensure that the state is not seen as a user state.
            settings.addInstance(new_instance)
            
        definition = stack.getSettingDefinition("material_flow")
        new_instance = SettingInstance(definition, settings)
        new_instance.setProperty("value", flow)
        new_instance.resetState()  # Ensure that the state is not seen as a user state.
        settings.addInstance(new_instance)

        definition = stack.getSettingDefinition("material_flow_layer_0")
        new_instance = SettingInstance(definition, settings)
        new_instance.setProperty("value", flow)
        new_instance.resetState()  # Ensure that the state is not seen as a user state.
        settings.addInstance(new_instance)
        
        active_build_plate = application.getMultiBuildPlateModel().activeBuildPlate
        node.addDecorator(BuildPlateDecorator(active_build_plate))

        node.addDecorator(SliceableObjectDecorator())

        application.getController().getScene().sceneChanged.emit(node)
        
    def _activateExtruder(self, ext_no) -> None:
        if ext_no == 0:
            #extruders = self._global_container_stack.extruderList
            #if not extruders[0].isEnabled:  
            self._application.getMachineManager().setExtruderEnabled(0, True)
            node.callDecoration("setActiveExtruder", 0)
            
        if ext_no == 1:
           # extruders = self._global_container_stack.extruderList
           # if not extruders[1].isEnabled:  
           self._application.getMachineManager().setExtruderEnabled(1, True)
           node.callDecoration("setActiveExtruder", 1) 
   
