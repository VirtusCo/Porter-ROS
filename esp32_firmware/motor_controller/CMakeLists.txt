cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(porter_motor_controller LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

target_sources(app PRIVATE
    src/main.cpp
)

# Add common shared code (protocol, CRC, transport)
target_sources(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/src/protocol.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/src/crc16.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/src/transport.c
)

target_include_directories(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../common/include
)
