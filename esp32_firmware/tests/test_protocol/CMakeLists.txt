cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(test_protocol LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

target_sources(app PRIVATE
    src/test_protocol.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/src/protocol.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/src/crc16.cpp
)

target_include_directories(app PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../../common/include
)
