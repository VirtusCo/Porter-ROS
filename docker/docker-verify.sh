#!/bin/bash
###############################################################################
# docker-verify.sh — Verify the Porter Robot Docker image built correctly
#
# Usage:
#   ./docker/docker-verify.sh [IMAGE_NAME]
#   Default IMAGE_NAME: docker-porter_dev:latest
#
# Runs a series of checks inside the container to confirm:
#   1. ROS 2 Jazzy environment is sourced correctly
#   2. All custom Porter packages are installed
#   3. Key ROS 2 system packages are available
#   4. YDLidar SDK is installed
#   5. Executables and entry points are findable
#   6. Launch files exist and can be listed
#   7. Config files are present
#   8. Python dependencies are importable
#   9. colcon test suite passes
#
# Run from repo root:
#   cd porter_robot/
#   ./docker/docker-verify.sh
###############################################################################

set -e

IMAGE="${1:-docker-porter_dev:latest}"
PASS=0
FAIL=0
WARN=0
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

run_check() {
    local name="$1"
    shift
    printf "  %-55s" "$name"
    if OUTPUT=$(docker run --rm "$IMAGE" "$@" 2>&1); then
        echo -e " [${GREEN}PASS${NC}]"
        PASS=$((PASS + 1))
    else
        echo -e " [${RED}FAIL${NC}]"
        echo "    Output: $OUTPUT" | head -3
        FAIL=$((FAIL + 1))
    fi
}

run_warn_check() {
    local name="$1"
    shift
    printf "  %-55s" "$name"
    if OUTPUT=$(docker run --rm "$IMAGE" "$@" 2>&1); then
        echo -e " [${GREEN}PASS${NC}]"
        PASS=$((PASS + 1))
    else
        echo -e " [${YELLOW}WARN${NC}]"
        echo "    Output: $OUTPUT" | head -3
        WARN=$((WARN + 1))
    fi
}

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Porter Robot — Docker Image Verification"
echo "  Image: $IMAGE"
echo "════════════════════════════════════════════════════════════"
echo ""

# ── Check image exists ──────────────────────────────────────────────────────
printf "  %-55s" "Image exists"
if docker image inspect "$IMAGE" > /dev/null 2>&1; then
    echo -e " [${GREEN}PASS${NC}]"
    PASS=$((PASS + 1))
else
    echo -e " [${RED}FAIL${NC}]"
    echo ""
    echo "    Image '$IMAGE' not found. Build it first with:"
    echo "      docker compose -f docker/docker-compose.dev.yml build"
    exit 1
fi

# ── ROS 2 Environment ───────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[ROS 2 Environment]${NC}"
run_check "ROS 2 Jazzy sourced (ROS_DISTRO=jazzy)"  \
    bash -c 'echo $ROS_DISTRO | grep -q jazzy'
run_check "ROS_DOMAIN_ID is 11"  \
    bash -c '[ "$ROS_DOMAIN_ID" = "11" ]'
run_check "RMW_IMPLEMENTATION is rmw_fastrtps_cpp"  \
    bash -c '[ "$RMW_IMPLEMENTATION" = "rmw_fastrtps_cpp" ]'
run_check "Workspace overlay sourced"  \
    bash -c 'echo $AMENT_PREFIX_PATH | grep -q workspace'

# ── Custom Packages ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Custom Porter Packages]${NC}"
run_check "ydlidar_driver installed"  \
    bash -c 'ros2 pkg prefix ydlidar_driver'
run_check "porter_lidar_processor installed"  \
    bash -c 'ros2 pkg prefix porter_lidar_processor'
run_check "porter_orchestrator installed"  \
    bash -c 'ros2 pkg prefix porter_orchestrator'

# ── System ROS 2 Packages ───────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[System ROS 2 Packages]${NC}"
run_check "rclcpp available"  \
    bash -c 'ros2 pkg prefix rclcpp'
run_check "rclpy available"  \
    bash -c 'ros2 pkg prefix rclpy'
run_check "sensor_msgs available"  \
    bash -c 'ros2 pkg prefix sensor_msgs'
run_check "diagnostic_msgs available"  \
    bash -c 'ros2 pkg prefix diagnostic_msgs'
run_check "std_msgs available"  \
    bash -c 'ros2 pkg prefix std_msgs'
run_check "std_srvs available"  \
    bash -c 'ros2 pkg prefix std_srvs'
run_check "tf2_ros available"  \
    bash -c 'ros2 pkg prefix tf2_ros'

# ── YDLidar SDK ─────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[YDLidar SDK]${NC}"
run_check "libydlidar_sdk.a installed"  \
    bash -c 'test -f /usr/local/lib/libydlidar_sdk.a'
run_check "SDK cmake config present"  \
    bash -c 'test -f /usr/local/lib/cmake/ydlidar_sdk/ydlidar_sdkConfig.cmake'
run_check "SDK headers present (CYdLidar.h)"  \
    bash -c 'test -f /usr/local/include/src/CYdLidar.h'

# ── Executables & Entry Points ──────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Executables & Entry Points]${NC}"
run_check "ydlidar_node binary"  \
    bash -c 'ros2 pkg executables ydlidar_driver | grep -q ydlidar_node'
run_check "processor_node entry point"  \
    bash -c 'ros2 pkg executables porter_lidar_processor | grep -q processor_node'
run_check "state_machine entry point"  \
    bash -c 'ros2 pkg executables porter_orchestrator | grep -q state_machine'
run_check "health_monitor entry point"  \
    bash -c 'ros2 pkg executables porter_orchestrator | grep -q health_monitor'

# ── Launch Files ────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Launch Files]${NC}"
run_check "ydlidar_launch.py"  \
    bash -c 'test -f $(ros2 pkg prefix ydlidar_driver)/share/ydlidar_driver/launch/ydlidar_launch.py'
run_check "ydlidar_rviz_launch.py"  \
    bash -c 'test -f $(ros2 pkg prefix ydlidar_driver)/share/ydlidar_driver/launch/ydlidar_rviz_launch.py'
run_check "processor_launch.py"  \
    bash -c 'test -f $(ros2 pkg prefix porter_lidar_processor)/share/porter_lidar_processor/launch/processor_launch.py'
run_check "orchestrator_launch.py"  \
    bash -c 'test -f $(ros2 pkg prefix porter_orchestrator)/share/porter_orchestrator/launch/orchestrator_launch.py'

# ── Configuration Files ─────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Configuration Files]${NC}"
run_check "ydlidar_params.yaml"  \
    bash -c 'test -f $(ros2 pkg prefix ydlidar_driver)/share/ydlidar_driver/config/ydlidar_params.yaml'
run_check "ydlidar_view.rviz"  \
    bash -c 'test -f $(ros2 pkg prefix ydlidar_driver)/share/ydlidar_driver/config/ydlidar_view.rviz'
run_check "processor_params.yaml"  \
    bash -c 'test -f $(ros2 pkg prefix porter_lidar_processor)/share/porter_lidar_processor/config/processor_params.yaml'
run_check "orchestrator_params.yaml"  \
    bash -c 'test -f $(ros2 pkg prefix porter_orchestrator)/share/porter_orchestrator/config/orchestrator_params.yaml'

# ── Python Dependencies ─────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Python Dependencies]${NC}"
run_check "numpy importable"  \
    bash -c "python3 -c 'import numpy'"
run_check "rclpy importable"  \
    bash -c "python3 -c 'import rclpy'"
run_check "sensor_msgs importable"  \
    bash -c "python3 -c 'from sensor_msgs.msg import LaserScan'"
run_check "diagnostic_msgs importable"  \
    bash -c "python3 -c 'from diagnostic_msgs.msg import DiagnosticArray'"
run_check "std_srvs importable"  \
    bash -c "python3 -c 'from std_srvs.srv import SetBool, Trigger'"

# ── Docker Entrypoint ───────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}[Docker Entrypoint]${NC}"
run_check "docker-entrypoint.sh exists"  \
    bash -c 'test -f /docker-entrypoint.sh'
run_check "docker-entrypoint.sh is executable"  \
    bash -c 'test -x /docker-entrypoint.sh'

# ── Test Suite (optional — slower) ──────────────────────────────────────────
echo ""
echo -e "${CYAN}[Test Suite]${NC}"
printf "  %-55s" "colcon test (99 tests)"
if OUTPUT=$(docker run --rm "$IMAGE" bash -c \
    'cd /workspace && colcon test --event-handlers console_direct+ 2>&1 && colcon test-result 2>&1' 2>&1); then
    # Extract test count from output
    SUMMARY=$(echo "$OUTPUT" | grep -oP '\d+ tests, \d+ errors, \d+ failures' | tail -1)
    if echo "$OUTPUT" | grep -q "0 errors, 0 failures"; then
        echo -e " [${GREEN}PASS${NC}]  ($SUMMARY)"
        PASS=$((PASS + 1))
    else
        echo -e " [${RED}FAIL${NC}]  ($SUMMARY)"
        FAIL=$((FAIL + 1))
    fi
else
    SUMMARY=$(echo "$OUTPUT" | grep -oP '\d+ tests, \d+ errors, \d+ failures' | tail -1)
    echo -e " [${RED}FAIL${NC}]  ($SUMMARY)"
    echo "    Run manually for details:"
    echo "      docker run --rm $IMAGE bash -c 'cd /workspace && colcon test --event-handlers console_direct+ && colcon test-result --verbose'"
    FAIL=$((FAIL + 1))
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════"
TOTAL=$((PASS + FAIL + WARN))
echo -e "  Results: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, ${YELLOW}$WARN warnings${NC} out of $TOTAL checks"
echo "════════════════════════════════════════════════════════════"
echo ""

if [ "$FAIL" -gt 0 ]; then
    echo -e "  ${RED}Some checks failed.${NC} Review the output above."
    echo ""
    echo "  Common fixes:"
    echo "    1. Rebuild:   docker compose -f docker/docker-compose.dev.yml build"
    echo "    2. Clean:     docker compose -f docker/docker-compose.dev.yml build --no-cache"
    echo "    3. Shell in:  docker run --rm -it $IMAGE bash"
    echo ""
    exit 1
else
    echo -e "  ${GREEN}All checks passed!${NC} The image is ready."
    echo ""
    echo "  Quick start:"
    echo "    docker compose -f docker/docker-compose.dev.yml up -d"
    echo "    docker exec -it porter_dev bash"
    echo ""
    exit 0
fi
