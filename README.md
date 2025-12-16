# mujoco_ros2_control_examples

## How to run

### Clone and build example repository

Before clone the repo, please make sure you have [`mujoco_ros2_control`](https://github.com/wei-hsuan-cheng/mujoco_ros2_control)  installed.
```bash
cd ~/ros2_ws/src
git clone https://github.com/wei-hsuan-cheng/mujoco_ros2_control_examples.git -b humble
cd ~/ros2_ws
colcon build --symlink-install && . install/setup.bash
```

### Running demos (collision/contact physical interactions invovled)
```bash
# Marker control
ros2 launch interactive_marker interactive_marker.launch.py task:=push_load # or peg_in_hole
# Ped-in-hole manipulation task
ros2 launch peg_in_hole peg_in_hole.launch.py
```

### Troubleshooting
```bash
# Ensure kinematics pluging is installed
sudo apt install ros-humble-kinematics-interface* -y
```