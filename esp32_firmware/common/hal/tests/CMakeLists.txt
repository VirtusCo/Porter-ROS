cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(vhal_tests)

target_sources(app PRIVATE
    test_hal_registry.c
    test_hal_sensor_mock.c
    test_hal_actuator_mock.c
    ../src/hal_core.c
    ../src/hal_health.c
    ../src/hal_error.c
)

target_include_directories(app PRIVATE ../include)
