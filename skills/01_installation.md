# ROS 2 Installation — Skill File

> Source: https://docs.ros.org/en/jazzy/Installation.html
> Distro: Jazzy Jalisco

---

## Binary Packages (Tier 1 Platforms)

### Ubuntu Linux (amd64 / aarch64) — Noble Numbat (24.04)
- **deb packages** (recommended): `sudo apt install ros-jazzy-desktop`
- **binary archive**: alternative if no root access

### Red Hat Enterprise Linux 9 (amd64)
- **RPM packages** (recommended)
- **binary archive**: alternative

### Windows 10 (amd64)
- **Binary archive** (VS 2019)

---

## Building from Source

Supported platforms:
- Ubuntu Linux 24.04
- Windows 10
- RHEL-9/Fedora
- macOS

---

## Which Install to Choose?

| Goal | Recommendation |
|---|---|
| General use, quick start | Binary packages (debs/RPMs) |
| No root access (Linux) | Binary archive |
| Alter/omit parts of ROS 2 | Build from source |
| Latest cutting-edge features | Build from source |
| Contributing to ROS 2 core | Build from source (Rolling) |

### Binary Packages Advantages
- Installs dependencies automatically.
- Updates alongside system updates.
- Requires root (deb/RPM only).

---

## RMW Implementations

The default RMW for Jazzy can be overridden. Available implementations:
- `rmw_fastrtps_cpp` (default)
- `rmw_cyclonedds_cpp`
- `rmw_connextdds`

Set via environment variable:
```bash
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
```

---

## Key Installation Commands (Ubuntu 24.04 Debs)

```bash
# Setup sources
sudo apt install software-properties-common
sudo add-apt-repository universe
sudo apt update && sudo apt install curl -y
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" | \
  sudo tee /etc/apt/sources.list.d/ros2.list > /dev/null

# Install
sudo apt update
sudo apt install ros-jazzy-desktop  # Full desktop install
# OR
sudo apt install ros-jazzy-ros-base  # Bare bones (no GUI)

# Source setup
source /opt/ros/jazzy/setup.bash
```

---

## Docker-Based Installation

For non-Tier-1 platforms or isolated environments:
```bash
docker pull osrf/ros:jazzy-desktop
docker run -it osrf/ros:jazzy-desktop bash
```

See: How-To Guide "Running ROS 2 nodes in Docker"

---

## Post-Installation Verification

```bash
# Terminal 1
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_cpp talker

# Terminal 2
source /opt/ros/jazzy/setup.bash
ros2 run demo_nodes_py listener
```

If the listener receives messages from the talker, installation is successful.
