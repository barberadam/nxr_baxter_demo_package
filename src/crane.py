#!/usr/bin/env python

# Jon Rovira
# Summer 2013

################
# ROS IMPORTS: #
################
import roslib
import rospy
from std_msgs.msg import UInt16

####################
# RETHINK IMPORTS: #
####################
import baxter_interface

###############
# NU IMPORTS: #
###############
from trajectory import Trajectory
from vector_operations import (make_vector_from_POINTS,
	                           angle_between_vectors,
	                           vector_projection_onto_plane,
	                           shortest_vector_from_point_to_vector)

##################
# OTHER IMPORTS: #
##################
import operator
import math

class Crane():
    """
    Crane control class

    This class allows Baxter to mimic an inidividual's left arm with Baxter's
    right arm and grants the individual control of Baxter's gripper. The Crane
    obtains tracking data by subscribing to the /skeleton messages published
    by the skeletontracker_nu script.
    """

    def __init__(self):
        """
        Crane constructor
        """
        rospy.logdebug("Calling Crane().__init__")
        # Get access to the right arm and gripper
        self.arm = baxter_interface.Limb('right')
        self.gripper = baxter_interface.Gripper('right')
        # define the neutral position for the crane game right arm
        self.neutral_position = dict(zip(self.arm.joint_names(),
                                         [0.00, 0.00, 1.57, 0.00, 0.00, 0.00, 0.00]))
        # We will always want the left arm in this position
        self.crane_l_angles = {'left_s0': 0.35, 'left_s1': 0.00,
                               'left_e0': 0.00, 'left_e1': 1.57,
                               'left_w0': 0.00, 'left_w1': 0.00,
                               'left_w2': 0.00}
        # Activate the gripper
        self.gripper_state = True
        self.gripper_state_timer = 0

    def desired_joint_vals(self, left_shoulder, left_elbow, left_hand,
                           right_shoulder, right_elbow, right_hand):
        """
        Returns the joint values based on the human skeleton.
        """
        rospy.logdebug("Calling Crane().desired_joint_vals(...)")
        # Initialize a list of angles that we will return.  This is probably not
        # the best way to do it, but this is how Jon did it orginally and Adam
        # wanted to match.
        angles = []
        # Both fills in 'angles' list and checks if the gripper should be open or closed
        if self.human_to_baxter(left_shoulder, left_elbow, left_hand,
                                right_shoulder, right_elbow, right_hand, angles):
            self.gripper.close()
        else:
            self.gripper.open()

        # Stores the positions for the right arm in the standard dictionary for arm values
        r_positions = dict(zip(self.arm.joint_names(),
                                [angles[0], angles[1], angles[2], angles[3],
                                angles[4], angles[5], angles[6]]))
        # Returns the combined dictionary for all joints
        return dict(self.crane_l_angles, **r_positions)

    def desired_pose_vals(self, left_shoulder, left_elbow, left_hand,
                          right_shoulder, right_elbow, right_hand, torso):
        """
        Returns the pose values based on the human skeleton. Similar to
        desired_joint_vals. Currently not working as ideal.
        """
        rospy.logdebug("Calling Crane().desired_pose_vals(...)")
        # Use length of arms to potentially calculate a useful scaling
        arm_length = (math.sqrt(math.pow((left_shoulder.x - left_elbow.x),2) +
                                math.pow((left_shoulder.y - left_elbow.y),2) +
                                math.pow((left_shoulder.z - left_elbow.z),2)) +
                        math.sqrt(math.pow((left_elbow.x - left_hand.x),2) +
                                math.pow((left_elbow.y - left_hand.y),2) +
                                math.pow((left_elbow.z - left_hand.z),2)))
        RJ_ARM_LENGTH = 41*2.54/100.0
        #From URDF, offsets from base/torso to right_uper_shoulder.
        # x_offset = 0.062
        # y_offset = -0.259
        # z_offset = 0.120

        # Baxter: x out, y left, z up from his perspective
        # Kinect: x right, y down, z out from its perspective
        # Best ones so far!
        # x = (-left_hand.z + torso.z)
        # y = (-torso.x + left_hand.x)
        # z = (-torso.y + left_hand.y)
        # x = (-left_hand.z + left_shoulder.z)*RJ_ARM_LENGTH/arm_length + x_offset
        # y = (left_hand.x - left_shoulder.x)*RJ_ARM_LENGTH/arm_length + y_offset
        # z = (-left_hand.y + left_shoulder.y)*RJ_ARM_LENGTH/arm_length + z_offset

        # scaling = RJ_ARM_LENGTH/arm_length
        scaling = 1.0
        # Introduce a small offset
        x = (torso.z - left_hand.z)*scaling + 0.2
        y = (left_hand.x - torso.x)*scaling
        z = (torso.y - left_hand.y)*scaling - 0.3
        # print "x: ", x
        # print "y: ", y
        # print "z: ", z
        # print self.arm.endpoint_pose()

        # Set orientation
        roll = 0 # Could be defined to be in line with the arm or something
        pitch = math.pi # Could be defined to be in line with the arm or something
        yaw = 0
        pose = {'x': x, 'y': y, 'z': z, 'roll': roll, 'pitch': pitch, 'yaw': yaw}

        # Gripper Control Arm
        r_upper_arm = make_vector_from_POINTS(right_shoulder, right_elbow)
        r_forearm = make_vector_from_POINTS(right_elbow, right_hand)
        # Event
        theta = angle_between_vectors(r_upper_arm, r_forearm)
        if theta > 0.8:
            self.gripper.close()
        else:
            self.gripper.open()

        return pose

    def human_to_baxter(self, l_sh, l_el, l_ha, r_sh, r_el, r_ha, a):
        """
        Computes angles sent to Baxter's arm, checks if gripper should adjust
        """
        rospy.logdebug("Calling Crane().human_to_baxter(...)")
        # Crane Arm
        # Forms vectors between points in 3-space and uses that and
        # vector operations to calculate the angles.
        l_upper_arm = make_vector_from_POINTS(l_sh, l_el)
        l_forearm = make_vector_from_POINTS(l_el, l_ha)
        # S0
        v_xz = vector_projection_onto_plane(l_upper_arm, [0,0,-1], [-1,0,0])
        theta = angle_between_vectors(v_xz, [-1,0,0])
        s0 = theta - math.pi/4
        # S1
        theta = angle_between_vectors(l_upper_arm, v_xz)
        if l_el.y > l_sh.y:
            s1 = theta
        else:
            s1 = -theta
        # E0
        n_upper_arm = shortest_vector_from_point_to_vector(l_ha, l_upper_arm,
                                                           l_forearm, l_sh)
        theta = angle_between_vectors(n_upper_arm, [0,1,0])
        e0 = theta
        # E1
        theta = angle_between_vectors(l_upper_arm, l_forearm)
        e1 = theta
        # W0, W1, and W2
        w0 = -1.57
        w1 = 0.00
        w2 = -0.30
        # Check if angles are valid
        self.check_angles(s0,s1,e0,e1,w0,w1,w2,a)

        # Gripper Control Arm
        r_upper_arm = make_vector_from_POINTS(r_sh, r_el)
        r_forearm = make_vector_from_POINTS(r_el, r_ha)
        # Event
        theta = angle_between_vectors(r_upper_arm, r_forearm)
        if theta > 0.8:
            return True
        return False

    def check_angles(self, s0, s1, e0, e1, w0, w1, w2, angles):
        """
        This function checks if the desired angles will be within the constraints.
        """
        rospy.logdebug("Calling Crane().check_angles(...)")
        if -0.25 < s0 and s0 < 1.60:
            angles.append(s0)
        elif -0.25 < s0:
            angles.append(1.60)
        else:
            angles.append(-0.25)

        # s1 assignment in safe range
        if -2.00 < s1 and s1 < 0.90:
            angles.append(s1)
        elif -2.00 < s1:
            angles.append(0.90)
        else:
            angles.append(-2.00)

        # e0 assignment
        angles.append(e0)

        # e1 assignment in safe range
        if 0.10 < e1 and e1 < 2.50:
            angles.append(e1)
        elif 0.10 < e1:
            angles.append(2.50)
        else:
            angles.append(0.10)

        # w0, w1, and w2 assignment
        angles.extend([w0,w1,w2])
