# ROS 2 Tutorials: Miscellaneous — Skill File

> Source: https://docs.ros.org/en/jazzy/Tutorials/Miscellaneous.html
> Distro: Jazzy Jalisco

---

## Sub-Documents

1. **Deploying on IBM Cloud Kubernetes** [community-contributed]
2. **Using Eclipse Oxygen with rviz2** [community-contributed]
3. **Building a real-time Linux kernel** [community-contributed]
4. **Building a package with Eclipse 2021-06**

---

## Real-Time Linux Kernel (rt_preempt)

### Purpose
Build a PREEMPT_RT kernel for deterministic real-time ROS 2 applications.

### When to Use
- Robot control loops requiring < 1ms jitter
- Safety-critical applications
- Hard real-time sensor processing

### High-Level Steps
1. Download kernel source matching your running kernel
2. Download corresponding rt_preempt patch
3. Apply patch: `patch -p1 < patch-<version>-rt<N>.patch`
4. Configure kernel: `make menuconfig` → enable `PREEMPT_RT_FULL`
5. Build: `make -j$(nproc) deb-pkg`
6. Install: `sudo dpkg -i linux-*.deb`
7. Reboot and verify: `uname -a` (should show `PREEMPT_RT`)

### RT Programming Best Practices with ROS 2
- Lock memory: `mlockall(MCL_CURRENT | MCL_FUTURE)`
- Use SCHED_FIFO or SCHED_RR scheduling
- Avoid dynamic memory allocation in hot paths (use TLSF allocator)
- Use `MultiThreadedExecutor` with dedicated threads for RT callbacks
- Set thread priorities appropriately

---

## Eclipse IDE Integration

### Setup for ROS 2 Package Development
1. Install Eclipse C/C++ Development Tools
2. Import as CMake project
3. Set build directory to `build/<package_name>`
4. Configure include paths for ROS 2:
   - `/opt/ros/jazzy/include/**`
   - Workspace `install/*/include/**`
5. Set environment: `source /opt/ros/jazzy/setup.bash` before launching Eclipse

---

## Cloud / Kubernetes Deployment

### ROS 2 on Kubernetes Considerations
- Use `host` network mode or configure DDS discovery across pods
- Set `ROS_DOMAIN_ID` consistently across containers
- Consider FastDDS Discovery Server for cross-node discovery
- Use PersistentVolumes for rosbag storage
- Health checks via lifecycle node states
