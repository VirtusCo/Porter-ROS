#!/bin/bash
###############################################################################
# docker-entrypoint.sh — Porter Robot Docker Entrypoint
#
# Sources ROS 2 Jazzy + workspace overlay, sets sensible defaults for
# ROS_DOMAIN_ID and RMW_IMPLEMENTATION, then exec's the container command.
###############################################################################
set -e

# ── Source ROS 2 Jazzy base ─────────────────────────────────────────────────
source /opt/ros/jazzy/setup.bash

# ── Source workspace overlay (if built) ─────────────────────────────────────
if [ -f /workspace/install/setup.bash ]; then
    source /workspace/install/setup.bash
fi

# ── Default environment variables (overridable at runtime with -e) ──────────
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-11}"
export RMW_IMPLEMENTATION="${RMW_IMPLEMENTATION:-rmw_fastrtps_cpp}"

# ── AI Assistant venv (add to PATH so `python3` from venv is available) ─────
if [ -d /workspace/ai_venv ]; then
    export PORTER_AI_VENV=/workspace/ai_venv
    export PATH="/workspace/ai_venv/bin:$PATH"
fi
# ── Process priority (nice) for SLAM coexistence ───────────────────────
# Set PORTER_NICE=10 in docker-compose to lower AI priority vs SLAM/Nav2.
# Only applies if PORTER_NICE is set and non-zero.
if [ -n "${PORTER_NICE:-}" ] && [ "${PORTER_NICE}" != "0" ]; then
    exec nice -n "${PORTER_NICE}" "$@"
fi
# ── Execute the container command ───────────────────────────────────────────
exec "$@"
