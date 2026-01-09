import os
import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, RegisterEventHandler
from launch.conditions import IfCondition, UnlessCondition
from launch.event_handlers import OnProcessStart, OnProcessExit
from launch.substitutions import (
    LaunchConfiguration,
    PathJoinSubstitution,
    PythonExpression,
)
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory
from launch_ros.actions import ComposableNodeContainer
from launch_ros.descriptions import ComposableNode
from moveit_configs_utils import MoveItConfigsBuilder

def load_yaml(package_name, file_path):
    package_path = get_package_share_directory(package_name)
    absolute_file_path = os.path.join(package_path, file_path)

    try:
        with open(absolute_file_path, "r") as file:
            return yaml.safe_load(file)
    except EnvironmentError:  # parent of IOError, OSError *and* WindowsError where available
        return None

def generate_launch_description():

    task = LaunchConfiguration("task")
    mujoco_sim = LaunchConfiguration("mujoco_sim")
    use_sim_time = mujoco_sim
    ros2_control_hardware_type = PythonExpression(
        ["'mujoco' if '", mujoco_sim, "' == 'true' else 'mock_components'"]
    )

    moveit_config = (
        MoveItConfigsBuilder("moveit_resources_panda")
        .robot_description(
            file_path="config/panda.urdf.xacro",
            mappings={
                "ros2_control_hardware_type": ros2_control_hardware_type,
            },
        )
        .robot_description_semantic(file_path="config/panda.srdf")
        .trajectory_execution(file_path="config/gripper_moveit_controllers.yaml")
        .planning_pipelines(pipelines=["ompl", "pilz_industrial_motion_planner"])
        .to_moveit_configs()
    )
    
    # Get parameters for the Servo node
    servo_yaml = load_yaml("moveit_servo", "config/panda_simulated_config.yaml")
    servo_params = {"moveit_servo": servo_yaml}

    # Start the actual move_group node/action server
    move_group_node = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            moveit_config.to_dict(), 
            {"use_sim_time": use_sim_time},
            ]
    )

    # RViz
    rviz_config_file = os.path.join(
        get_package_share_directory("interactive_marker"),
        "config",
        "open_door1.rviz",
    )
    # rviz_config_file = (
    #     get_package_share_directory("moveit_servo") + "/config/demo_rviz_config.rviz"
    # )

    rviz_node = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", rviz_config_file],
        parameters=[
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            moveit_config.planning_pipelines,
            moveit_config.joint_limits,
            {"use_sim_time": use_sim_time},
        ],
    )

    # Static TF
    world2robot_tf_node = Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name="static_transform_publisher",
        output="log",
        arguments=["--frame-id", "world", "--child-frame-id", "panda_link0"],
        parameters=[
            {"use_sim_time": use_sim_time},
            ],
    )

    # Publish TF
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        name="robot_state_publisher",
        output="both",
        parameters=[
            moveit_config.robot_description, 
            {"use_sim_time": use_sim_time},
            ],
    )

    # ros2_control using FakeSystem as hardware
    ros2_controllers_path = os.path.join(
        get_package_share_directory("moveit_resources_panda_moveit_config"),
        "config",
        "ros2_controllers.yaml",
    )
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            moveit_config.robot_description, 
            ros2_controllers_path,
            {"use_sim_time": use_sim_time},
            ],
        output="screen",
        condition=UnlessCondition(mujoco_sim),
    )

    mujoco_model_filename = PythonExpression(
        ["'scene_' + '", task, "' + '.xml'"]
    )

    mujoco_model_path = PathJoinSubstitution([
        FindPackageShare("panda_mujoco"),
        "franka_emika_panda",
        mujoco_model_filename,
    ])

    mujoco_ros2_control_node = Node(
        package='mujoco_ros2_control',
        executable='mujoco_ros2_control',
        output='screen',
        parameters=[
            moveit_config.robot_description,
            ros2_controllers_path,
            {'mujoco_model_path': mujoco_model_path},
            {"use_sim_time": use_sim_time}
        ],
        condition=IfCondition(mujoco_sim),
    )
    
    # control_node = either ros2_control_node or mujoco_ros2_control_node
    control_node = mujoco_ros2_control_node if mujoco_sim else ros2_control_node

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
        ],
    )

    panda_arm_controller_unchained_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["panda_arm_controller_unchained", "-c", "/controller_manager"],
    )

    panda_hand_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["panda_hand_controller", "-c", "/controller_manager"],
    )
    
    ft_sensor_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["force_torque_broadcaster", "-c", "/controller_manager"],
    )
    
    # Launch as much as possible in components
    container = ComposableNodeContainer(
        name="moveit_servo_demo_container",
        namespace="/",
        package="rclcpp_components",
        executable="component_container_mt",
        composable_node_descriptions=[
            # Example of launching Servo as a node component
            # Assuming ROS2 intraprocess communications works well, this is a more efficient way.
            # ComposableNode(
            #     package="moveit_servo",
            #     plugin="moveit_servo::ServoServer",
            #     name="servo_server",
            #     parameters=[
            #         servo_params,
            #         moveit_config.robot_description,
            #         moveit_config.robot_description_semantic,
            #     ],
            # ),
            ComposableNode(
                package="moveit_servo",
                plugin="moveit_servo::JoyToServoPub",
                name="controller_to_servo_node",
            ),
            ComposableNode(
                package="joy",
                plugin="joy::Joy",
                name="joy_node",
            ),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
        output="screen",
    )
    
    servo_node = Node(
        package="moveit_servo",
        executable="servo_node_main",
        parameters=[
            servo_params,
            moveit_config.robot_description,
            moveit_config.robot_description_semantic,
            moveit_config.robot_description_kinematics,
            {"use_sim_time": use_sim_time},
        ],
        remappings=[
            ("/panda_arm_controller/joint_trajectory", "/panda_arm_controller_unchained/joint_trajectory"),
        ],
        output="screen",
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "task",
                default_value="open_door",
                description="Task name (e.g. 'open_door', 'peg_in_hole', or 'push_load')",
            ),
            DeclareLaunchArgument(
                "mujoco_sim",
                default_value="false",
                description="Use MuJoCo simulator",
            ),
            
            # RegisterEventHandler(
            #     event_handler=OnProcessStart(
            #         target_action=control_node,
            #         on_start=[
            #             joint_state_broadcaster_spawner,
            #             ],
            #     )
            # ),
            
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=joint_state_broadcaster_spawner,
                    on_exit=[
                        panda_hand_controller_spawner, 
                        ft_sensor_broadcaster_spawner,
                        ],
                )
            ),
            
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action =panda_hand_controller_spawner,
                    on_exit=[
                        panda_arm_controller_unchained_spawner,
                             ],
                )
            ),
            
            rviz_node,
            ros2_control_node,
            # control_node,
            world2robot_tf_node,
            robot_state_publisher,
            move_group_node,
            joint_state_broadcaster_spawner,
            mujoco_ros2_control_node,
            servo_node,
            container,
        ]
    )
