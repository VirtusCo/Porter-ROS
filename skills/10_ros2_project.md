# ROS 2 Project: Contributing, Governance & Features — Skill File

> Source: https://docs.ros.org/en/jazzy/The-ROS2-Project.html
> Distro: Jazzy Jalisco

---

## The ROS 2 Project Overview

The ROS 2 Project section covers:
- Contributing guidelines and processes
- Feature status and roadmap
- Project governance
- Platform policies

---

## Contributing

### Sub-Pages
1. **Developer Guide** → see `skills/ros2_developer_guide.md`
2. **Code Style and Language Versions** → see `skills/ros2_code_style.md`
3. **Quality Guide** → see `skills/ros2_quality_guide.md`
4. **ROS Build Farms** — CI infrastructure at ci.ros2.org
5. **Windows Tips and Tricks** — Windows-specific dev guidance
6. **Contributing to ROS 2 Documentation** — Docs contribution guide

---

## Features Status

ROS 2 tracks feature implementation status across distributions. Key feature areas:

### Core Features
- **Discovery**: DDS-based, configurable domain ID, discovery server option
- **Communication**: Topics, Services, Actions all fully supported
- **Parameters**: Typed, declared, runtime-changeable with callbacks
- **Lifecycle Nodes**: Full state machine (configure/activate/deactivate/cleanup/shutdown)
- **Component Composition**: Load multiple nodes in single process
- **Launch System**: Python, XML, YAML — fully featured

### Quality & Testing
- **ament_lint tools**: Full suite for C++, Python, CMake
- **Testing frameworks**: GTest, pytest, launch_testing
- **Code coverage**: lcov integration, buildfarm coverage reports
- **Thread Safety Analysis**: Clang-based static analysis with TSA macros

### Middleware
- **Fast DDS** (default): Full-featured, shared memory, discovery server
- **Cyclone DDS**: Lightweight, performant
- **Connext DDS**: Commercial, enterprise features
- **Zenoh**: Experimental non-DDS transport

### Security
- DDS Security implementation
- Authentication, access control, cryptography
- Security enclaves and keystore management

### Tooling
- **ros2 CLI**: Comprehensive command-line interface
- **RQt**: Qt-based GUI plugins
- **RViz2**: 3D visualization
- **rosbag2**: Data recording and playback
- **ros2doctor**: Diagnostic tool
- **ros2_tracing**: LTTng-based performance tracing

---

## Feature Ideas

Community-sourced feature ideas tracked on GitHub. Anyone can propose features.

Key areas of active development:
- Improved real-time support
- Better embedded/resource-constrained support
- Enhanced security features
- Better developer experience and tooling
- Performance improvements

---

## Roadmap

Each distribution has a roadmap produced by:
- ROS Boss + ROS 2 dev team lead
- ROS 2 TSC (Technical Steering Committee)
- Community contributors

Tracked via GitHub issues in `ros2/ros2` repository.

---

## Project Governance

### Technical Steering Committee (TSC)
- Guides technical direction of ROS 2
- Members from diverse organizations
- Regular meetings (open to public)

### Package Maintainers
- Defined in `package.xml` `<maintainer>` tags
- Responsible for:
  - Reviewing and merging PRs
  - Releasing packages
  - Maintaining quality standards
  - Backporting fixes

### Committers
- Have merge permissions on repositories
- Listed in governance documentation

---

## Platform EOL Policy

- Platforms follow OS vendor support lifecycles
- ROS 2 drops platform support when OS vendor drops it
- Target platforms set per-distribution via REP-2000
- Jazzy targets:
  - Ubuntu 24.04 (amd64, aarch64)
  - RHEL 9 (amd64)
  - Windows 10 (amd64)

---

## ROSCon Content

Annual ROS developer conference with talks and workshops.
Recordings available at: https://roscon.ros.org/

---

## Metrics

ROS ecosystem metrics tracked:
- Package counts per distribution
- Download statistics
- Repository activity
- Community size

Available at: https://metrics.ros.org/
