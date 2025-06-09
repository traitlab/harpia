import csv
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom.minidom import parseString

from lib.config import config

class BuildWaylinesWPML:

    # -------------------------------------------------------------------------
    def __init__(self):

        self.wpt_csv_properties = None
        self.cpt_csv_properties = None

        self.waypointSpeed = '15'
        self.waypointSpeed_approach = '3'
        # waypointTurnParam
        self.waypointTurnMode = 'toPointAndStopWithDiscontinuityCurvature'
        self.waypointTurnDampingDist = '0'

        # waypointGimbalHeadingParam
        self.waypointGimbalPitchAngle = '0'
        self.waypointGimbalYawAngle = '0'

        self.waypointWorkType= '0'

        # Variables for common values
        self.use_straight_line = '1'

        self.waypoint_heading_mode = 'followWayline'
        self.waypoint_heading_angle = '0'
        self.waypoint_heading_angle_enable = '0'
        self.waypoint_poi_point = '0.000000,0.000000,0.000000'
        self.waypoint_heading_poi_index = '0'

        self.action_group_mode = 'sequence'
        self.action_trigger_type = 'reachPoint'

        # self.action_id = '0'
        self.action_actuator_func = 'orientedShoot'
        self.gimbal_pitch_rotate_angle = '-90'
        self.gimbal_roll_rotate_angle = '0'
        self.gimbal_yaw_rotate_angle = '0'
        self.focus_x = '0'
        self.focus_y = '0'
        self.focus_region_width = '0'
        self.focus_region_height = '0'

        self.gimbalRotateMode = 'absoluteAngle'
        self.gimbalPitchRotateEnable = '1'
        self.gimbalRollRotateEnable = '0'
        self.gimbalRollRotateAngle = '0'
        self.gimbalYawRotateEnable = '0'
        self.gimbalYawRotateAngle = '0'
        self.gimbalRotateTimeEnable = '0'
        self.gimbalRotateTime = '0'
        self.payloadPositionIndex = '0'

        self.aircraft_heading = '0'
        self.accurate_frame_valid = '0'
        self.payload_position_index = '0'
        self.use_global_payload_lens_index = '0'
        self.target_angle = '0'
        self.image_width = '0'
        self.image_height = '0'
        self.af_pos = '0'
        self.gimbal_port = '0'
        self.oriented_camera_type = '67'
        self.oriented_file_size = '0'
        self.orientedCameraShutterTime = '0.00625'

        self.oriented_photo_mode = 'normalPhoto'
        self.is_risky = '0'
        
        # Define namespaces
        self.namespaces = {
            'kml': 'http://www.opengis.net/kml/2.2',
            'wpml': 'http://www.dji.com/wpmz/1.0.6'
        }

    # -------------------------------------------------------------------------
    def read_points_csv(self, csv_file, type):
        properties = []
        with open(csv_file, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row['type'] != type :
                  continue
                lon_x = row['lon_x']
                lat_y = row['lat_y']
                elevation_from_dsm = row['elevation_from_dsm']
                polygon_id = row['polygon_id']
                properties.append((lat_y, lon_x, elevation_from_dsm, polygon_id))

        # Check if the first and last points are the same and remove the last point if they are
        if len(properties) > 1 and properties[0] == properties[-1]:
            properties.pop()

        return properties

    # -------------------------------------------------------------------------
    def setup(self):
        # Read the coordinates from the CSV
        self.wpt_csv_properties = self.read_points_csv(
            config.points_csv_file_path, 'wpt')
        self.cpt_csv_properties = self.read_points_csv(
            config.points_csv_file_path, 'cpt')
        if len(self.wpt_csv_properties) < 2:
            self.cpt_csv_properties = self.wpt_csv_properties.copy()
            self.cpt_csv_properties.append(list(self.cpt_csv_properties[-1]))
            # sys.exit("Not enought wpt. Minimum of two wpt is supported. One wpt can be created directly using the drone remote.")
        elif len(self.wpt_csv_properties) != len(self.cpt_csv_properties) + 1:
            if len(self.wpt_csv_properties) > len(self.cpt_csv_properties) + 1:
              sys.exit("Two many wpt or not enought cpt. Number of wpt must be one more than the number of cpt points.")
            if len(self.wpt_csv_properties) < len(self.cpt_csv_properties) + 1:
              sys.exit("Too many cpt or not enought wpt. Number of wpt must be one more than the number of cpt points.")
        # Duplicate the first and last checkpoint property to make thing easier to handle the first and last waypoint 
        self.cpt_csv_properties.insert(0, self.cpt_csv_properties[0][:])
        self.cpt_csv_properties.append(list(self.cpt_csv_properties[-1]))

        # Register namespaces and parse the KML file
        ET.register_namespace('', "http://www.opengis.net/kml/2.2")
        ET.register_namespace('wpml', "http://www.dji.com/wpmz/1.0.6")

        # Parse the KML file
        self.tree = ET.parse(config.wpml_model_file_path)
        self.root = self.tree.getroot()

        # Find the Folder element
        self.folder = self.root.find('.//kml:Folder', self.namespaces)
        # Remove all existing Placemark elements with Point
        for placemark in self.folder.findall('kml:Placemark', self.namespaces):
            self.folder.remove(placemark)

    # -------------------------------------------------------------------------
    def generate(self):
        # Find the first checkpoint's elevation_from_dsm
        # The first check point is either at the same height than the frist tree or higher. So it's ok to use it as the first point altitude to reach. 
        # Safe takeoff altitude is set by the pilote (takeOffSecurityHeight is set to 100 in our templat_ye)  
        # Return to home altitude is also set on the drone remote by the pilote for the last point

        # Add new Placemark elements for each coordinate
        base_index = 0
        action_group_id = 0
        touch_sky_count = 0

        for idx, (lat_y, lon_x, wpt_elevation_from_dsm, polygon_id) in enumerate(self.wpt_csv_properties):
            cpt_elevation_from_dsm = self.cpt_csv_properties[idx][2]

            # Standard sequence
            height = str(float(cpt_elevation_from_dsm) + float(config.buffer) + float(config.approach))
            self.addTreeFirstLastPlacemark(
                base_index, lat_y, lon_x, height, polygon_id, '-90', action_group_id, base_index)
            
            height = str(float(wpt_elevation_from_dsm) + float(config.buffer) + float(config.approach))
            self.addTreeApproachPlacemark(
                base_index + 1, lat_y, lon_x, height, polygon_id)

            height = str(float(wpt_elevation_from_dsm) + float(config.buffer))
            self.addTreePhotosPlacemark(
                base_index + 2, lat_y, lon_x, height, polygon_id, action_group_id + 1, base_index + 2)
            
            cpt_elevation_from_dsm = self.cpt_csv_properties[idx+1][2]
            height = str(float(cpt_elevation_from_dsm) + float(config.buffer) + float(config.approach))
            self.addTreeFirstLastPlacemark(
                base_index + 3, lat_y, lon_x, height, polygon_id, '-15', action_group_id + 2, base_index + 3)
            
            touch_sky_count += 1

            # Add touch-sky action if enabled and interval is reached
            if config.touch_sky and touch_sky_count >= config.touch_sky_interval:
                height = str(float(cpt_elevation_from_dsm) + float(config.buffer) + float(config.approach) + float(config.touch_sky_altitude))
                self.addTouchSkyPlacemark(
                    base_index + 4, lat_y, lon_x, height, polygon_id, '-90', action_group_id + 3, base_index + 4)
                
                height = str(float(cpt_elevation_from_dsm) + float(config.buffer) + float(config.approach))
                self.addTreeFirstLastPlacemark(
                    base_index + 5, lat_y, lon_x, height, polygon_id, '-15', action_group_id + 4, base_index + 5)
                
                base_index += 6  # Increment by 6 when touch-sky is added
                action_group_id += 5  # Increment by 5 when touch-sky is added
                touch_sky_count = 0
            else:
                base_index += 4  # Normal increment by 4
                action_group_id += 3  # Normal increment by 3

    # -------------------------------------------------------------------------
    def addTreeFirstLastPlacemark(self, idx, lat_y, lon_x, height, polygon_id, gimbalPitchRotateAngle, actionGroupId, actionGroupIndex):
        # Add new Placemark elements for each coordinate
        # for idx, (lat_y, lon_x, elevation_from_dsm, polygon_id) in enumerate(self.csv_properties):
        placemark = ET.Element(f'{{{self.namespaces["kml"]}}}Placemark')

        point = ET.SubElement(placemark, f'{{{self.namespaces["kml"]}}}Point')
        coordinates_element = ET.SubElement(
            point, f'{{{self.namespaces["kml"]}}}coordinates')
        coordinates_element.text = f'{lon_x},{lat_y}'

        wpml_index = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}index')
        wpml_index.text = str(idx)

        wpml_executeHeight = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}executeHeight')
        wpml_executeHeight.text = height

        wpml_waypointSpeed = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointSpeed')
        wpml_waypointSpeed.text = self.waypointSpeed

        wpml_waypointHeadingParam = self.addWaypointHeadingParam()
        placemark.append(wpml_waypointHeadingParam)

        wpml_waypointTurnParam = self.addWaypointTurnParam()
        placemark.append(wpml_waypointTurnParam)

        wpml_use_straight_line = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}useStraightLine')
        wpml_use_straight_line.text = self.use_straight_line

        wpml_actionGroup = self.addPlacemarkActionGroup(actionGroupId, actionGroupIndex)
        placemark.append(wpml_actionGroup)

        wpml_action = self.addPlacemarkActionGimbalRotate('0', gimbalPitchRotateAngle)
        wpml_actionGroup.append(wpml_action)

        wpml_waypointGimbalHeadingParam = self.addWaypointGimbalHeadingParam()
        placemark.append(wpml_waypointGimbalHeadingParam)

        wpml_is_risky = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}isRisky')
        wpml_is_risky.text = self.is_risky

        wpml_waypointWorkType = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointWorkType')
        wpml_waypointWorkType.text = self.waypointWorkType

        self.folder.append(placemark)

    # -------------------------------------------------------------------------
    def addWaypointHeadingParam(self):
        wpml_waypointHeadingParam = ET.Element(f'{{{self.namespaces["wpml"]}}}waypointHeadingParam')

        wpml_waypointHeadingMode = ET.SubElement(
            wpml_waypointHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointHeadingMode')
        wpml_waypointHeadingMode.text = self.waypoint_heading_mode

        wpml_waypointHeadingAngle = ET.SubElement(
            wpml_waypointHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointHeadingAngle')
        wpml_waypointHeadingAngle.text = self.waypoint_heading_angle

        wpml_waypointPoiPoint = ET.SubElement(
            wpml_waypointHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointPoiPoint')
        wpml_waypointPoiPoint.text = self.waypoint_poi_point

        wpml_waypointHeadingAngleEnable = ET.SubElement(
            wpml_waypointHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointHeadingAngleEnable')
        wpml_waypointHeadingAngleEnable.text = self.waypoint_heading_angle_enable
        
        wpml_waypointHeadingPoiIndex = ET.SubElement(
            wpml_waypointHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointHeadingPoiIndex')
        wpml_waypointHeadingPoiIndex.text = self.waypoint_heading_poi_index

        return wpml_waypointHeadingParam

    # -------------------------------------------------------------------------
    def addWaypointTurnParam(self):
      wpml_waypointTurnParam = ET.Element(f'{{{self.namespaces["wpml"]}}}waypointTurnParam')

      wpml_waypointTurnMode = ET.SubElement(
          wpml_waypointTurnParam, f'{{{self.namespaces["wpml"]}}}waypointTurnMode')
      wpml_waypointTurnMode.text = self.waypointTurnMode
      
      wpml_waypointTurnDampingDist = ET.SubElement(
          wpml_waypointTurnParam, f'{{{self.namespaces["wpml"]}}}waypointTurnDampingDist')
      wpml_waypointTurnDampingDist.text = self.waypointTurnDampingDist

      return wpml_waypointTurnParam

    # -------------------------------------------------------------------------
    def addWaypointGimbalHeadingParam(self):
      wpml_waypointGimbalHeadingParam = ET.Element(f'{{{self.namespaces["wpml"]}}}waypointGimbalHeadingParam')

      wpml_waypointGimbalPitchAngle = ET.SubElement(
          wpml_waypointGimbalHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointGimbalPitchAngle')
      wpml_waypointGimbalPitchAngle.text = self.waypointGimbalPitchAngle
      
      wpml_waypointGimbalYawAngle = ET.SubElement(
          wpml_waypointGimbalHeadingParam, f'{{{self.namespaces["wpml"]}}}waypointGimbalYawAngle')
      wpml_waypointGimbalYawAngle.text = self.waypointGimbalYawAngle

      return wpml_waypointGimbalHeadingParam

    # -------------------------------------------------------------------------
    def addTreeApproachPlacemark(self, idx, lat_y, lon_x, height, polygon_id):
        # Add new Placemark elements for each coordinate
        # for idx, (lat_y, lon_x, elevation_from_dsm, polygon_id) in enumerate(self.csv_properties):
        placemark = ET.Element(f'{{{self.namespaces["kml"]}}}Placemark')

        point = ET.SubElement(placemark, f'{{{self.namespaces["kml"]}}}Point')
        coordinates_element = ET.SubElement(
            point, f'{{{self.namespaces["kml"]}}}coordinates')
        coordinates_element.text = f'{lon_x},{lat_y}'

        wpml_index = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}index')
        wpml_index.text = str(idx)

        wpml_executeHeight = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}executeHeight')
        wpml_executeHeight.text = height

        wpml_waypointSpeed = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointSpeed')
        wpml_waypointSpeed.text = self.waypointSpeed_approach

        wpml_waypointHeadingParam = self.addWaypointHeadingParam()
        placemark.append(wpml_waypointHeadingParam)

        wpml_waypointTurnParam = self.addWaypointTurnParam()
        placemark.append(wpml_waypointTurnParam)

        wpml_use_straight_line = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}useStraightLine')
        wpml_use_straight_line.text = self.use_straight_line

        wpml_waypointGimbalHeadingParam = self.addWaypointGimbalHeadingParam()
        placemark.append(wpml_waypointGimbalHeadingParam)

        wpml_is_risky = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}isRisky')
        wpml_is_risky.text = self.is_risky

        wpml_waypointWorkType = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointWorkType')
        wpml_waypointWorkType.text = self.waypointWorkType

        self.folder.append(placemark)

    # -------------------------------------------------------------------------
    def addPlacemarkActionGroup(self, action_group_id, action_group_index):
        action_group = ET.Element(f'{{{self.namespaces["wpml"]}}}actionGroup')
        ET.SubElement(
            action_group, f'{{{self.namespaces["wpml"]}}}actionGroupId').text = str(action_group_id)
        ET.SubElement(
            action_group, f'{{{self.namespaces["wpml"]}}}actionGroupStartIndex').text = str(action_group_index)
        ET.SubElement(
            action_group, f'{{{self.namespaces["wpml"]}}}actionGroupEndIndex').text = str(action_group_index)
        ET.SubElement(
            action_group, f'{{{self.namespaces["wpml"]}}}actionGroupMode').text = self.action_group_mode

        action_trigger = ET.SubElement(
            action_group, f'{{{self.namespaces["wpml"]}}}actionTrigger')
        ET.SubElement(
            action_trigger, f'{{{self.namespaces["wpml"]}}}actionTriggerType').text = self.action_trigger_type

        return action_group
    
    # -------------------------------------------------------------------------
    def addPlacemarkActionGimbalRotate(self, idx, gimbalPitchRotateAngle):
        action = ET.Element(f'{{{self.namespaces["wpml"]}}}action')
        ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionId').text = idx
        ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionActuatorFunc').text = 'gimbalRotate'

        action_actuator_func_param = ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionActuatorFuncParam')
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRotateMode').text = self.gimbalRotateMode
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalPitchRotateEnable').text = self.gimbalPitchRotateEnable
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalPitchRotateAngle').text = gimbalPitchRotateAngle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRollRotateEnable').text = self.gimbalRollRotateEnable
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRollRotateAngle').text = self.gimbalRollRotateAngle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalYawRotateEnable').text = self.gimbalYawRotateEnable
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalYawRotateAngle').text = self.gimbalYawRotateAngle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRotateTimeEnable').text = self.gimbalRotateTimeEnable
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRotateTime').text = self.gimbalRotateTime
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}payloadPositionIndex').text = self.payloadPositionIndex

        return action


    # -------------------------------------------------------------------------
    def addPlacemarkActionOrientedShoot(self, idx, focalLength, orientedFileSuffix, actionUUID, orientedFilePath):
        action = ET.Element(f'{{{self.namespaces["wpml"]}}}action')
        ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionId').text = idx
        ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionActuatorFunc').text = self.action_actuator_func

        action_actuator_func_param = ET.SubElement(
            action, f'{{{self.namespaces["wpml"]}}}actionActuatorFuncParam')
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalPitchRotateAngle').text = self.gimbal_pitch_rotate_angle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalRollRotateAngle').text = self.gimbal_roll_rotate_angle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalYawRotateAngle').text = self.gimbal_yaw_rotate_angle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}focusX').text = self.focus_x
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}focusY').text = self.focus_y
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}focusRegionWidth').text = self.focus_region_width
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}focusRegionHeight').text = self.focus_region_height
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}focalLength').text = focalLength
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}aircraftHeading').text = self.aircraft_heading
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}accurateFrameValid').text = self.accurate_frame_valid
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}payloadPositionIndex').text = self.payload_position_index
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}useGlobalPayloadLensIndex').text = self.use_global_payload_lens_index
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}targetAngle').text = self.target_angle
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}actionUUID').text = actionUUID
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}imageWidth').text = self.image_width
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}imageHeight').text = self.image_height
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}AFPos').text = self.af_pos
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}gimbalPort').text = self.gimbal_port
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedCameraType').text = self.oriented_camera_type
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedFilePath').text = orientedFilePath
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedFileMD5')
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedFileSize').text = self.oriented_file_size
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedFileSuffix').text = orientedFileSuffix
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedCameraShutterTime').text = self.orientedCameraShutterTime
        ET.SubElement(action_actuator_func_param,
                      f'{{{self.namespaces["wpml"]}}}orientedPhotoMode').text = self.oriented_photo_mode

        return action

    # -------------------------------------------------------------------------
    def addTreePhotosPlacemark(self, idx, lat_y, lon_x, elevation_from_dsm, polygon_id, actionGroupId, actionGroupIndex):
        placemark = ET.Element(f'{{{self.namespaces["kml"]}}}Placemark')

        point = ET.SubElement(placemark, f'{{{self.namespaces["kml"]}}}Point')
        coordinates_element = ET.SubElement(
            point, f'{{{self.namespaces["kml"]}}}coordinates')
        coordinates_element.text = f'{lon_x},{lat_y}'

        wpml_index = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}index')
        wpml_index.text = str(idx)

        wpml_executeHeight = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}executeHeight')
        wpml_executeHeight.text = elevation_from_dsm

        wpml_waypointSpeed = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointSpeed')
        wpml_waypointSpeed.text = self.waypointSpeed

        wpml_waypointHeadingParam = self.addWaypointHeadingParam()
        placemark.append(wpml_waypointHeadingParam)

        wpml_waypointTurnParam = self.addWaypointTurnParam()
        placemark.append(wpml_waypointTurnParam)

        wpml_useStraightLine = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}useStraightLine')
        wpml_useStraightLine.text = self.use_straight_line

        wpml_actionGroup = self.addPlacemarkActionGroup(actionGroupId, actionGroupIndex)
        placemark.append(wpml_actionGroup)

        wpml_action = self.addPlacemarkActionOrientedShoot('0', '168', str(
            polygon_id) + "zoom", '703556e4-81fb-4294-b607-05d5f748377f', '703556e4-81fb-4294-b607-05d5f748377f')
        wpml_actionGroup.append(wpml_action)

        wpml_action = self.addPlacemarkActionOrientedShoot('1', '24', str(
            polygon_id), '51ae7825-56de-41d3-90bb-3c9ed6de7960', '393e34ba-016e-4fd3-98bf-3f9fe0c517df')
        wpml_actionGroup.append(wpml_action)

        wpml_waypointGimbalHeadingParam = self.addWaypointGimbalHeadingParam()
        placemark.append(wpml_waypointGimbalHeadingParam)

        wpml_is_risky = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}isRisky')
        wpml_is_risky.text = self.is_risky

        wpml_waypointWorkType = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointWorkType')
        wpml_waypointWorkType.text = self.waypointWorkType

        self.folder.append(placemark)
    
    # -------------------------------------------------------------------------
    def addTouchSkyPlacemark(self, idx, lat_y, lon_x, height, polygon_id, gimbalPitchRotateAngle, actionGroupId, actionGroupIndex):
        placemark = ET.Element(f'{{{self.namespaces["kml"]}}}Placemark')

        point = ET.SubElement(placemark, f'{{{self.namespaces["kml"]}}}Point')
        coordinates_element = ET.SubElement(
            point, f'{{{self.namespaces["kml"]}}}coordinates')
        coordinates_element.text = f'{lon_x},{lat_y}'

        wpml_index = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}index')
        wpml_index.text = str(idx)

        wpml_executeHeight = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}executeHeight')
        wpml_executeHeight.text = height

        wpml_waypointSpeed = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointSpeed')
        wpml_waypointSpeed.text = self.waypointSpeed

        wpml_waypointHeadingParam = self.addWaypointHeadingParam()
        placemark.append(wpml_waypointHeadingParam)

        wpml_waypointTurnParam = self.addWaypointTurnParam()
        placemark.append(wpml_waypointTurnParam)

        wpml_use_straight_line = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}useStraightLine')
        wpml_use_straight_line.text = self.use_straight_line

        wpml_actionGroup = self.addPlacemarkActionGroup(actionGroupId, actionGroupIndex)
        placemark.append(wpml_actionGroup)

        wpml_action = self.addPlacemarkActionGimbalRotate('0', gimbalPitchRotateAngle)
        wpml_actionGroup.append(wpml_action)

        wpml_waypointGimbalHeadingParam = self.addWaypointGimbalHeadingParam()
        placemark.append(wpml_waypointGimbalHeadingParam)

        wpml_is_risky = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}isRisky')
        wpml_is_risky.text = self.is_risky

        wpml_waypointWorkType = ET.SubElement(
            placemark, f'{{{self.namespaces["wpml"]}}}waypointWorkType')
        wpml_waypointWorkType.text = self.waypointWorkType

        # Add hover action for 5 seconds ----- TODO

        self.folder.append(placemark)
    
    # -------------------------------------------------------------------------
    def saveNewWPML(self):
        # Reopen, beautify it, and save it
        pretty_xml_str = self.beautify_xml()

        # Save the updated WPML file
        wpml_path = Path(config.base_path) / config.base_name / \
            config.output_wpml_file_path
        os.makedirs(os.path.dirname(
            wpml_path), exist_ok=True)
        with open(wpml_path, 'w', encoding='UTF-8') as file:
            file.write(pretty_xml_str)

    # -------------------------------------------------------------------------
    def beautify_xml(self):

        # Convert the XML tree to a string
        xml_str = ET.tostring(self.tree.getroot(), encoding='unicode')

        # Parse the XML string
        dom = parseString(xml_str)

        # Pretty print the XML with an indentation of 2 spaces
        pretty_xml_str = dom.toprettyxml(indent="  ")

        # Remove empty lines
        non_empty_lines = [
            line for line in pretty_xml_str.splitlines() if line.strip() != ""]
        cleaned_pretty_xml_str = "\n".join(non_empty_lines)

        return cleaned_pretty_xml_str
