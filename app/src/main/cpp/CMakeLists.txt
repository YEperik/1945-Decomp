cmake_minimum_required(VERSION 3.22.1)
project(1945portcore C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

get_filename_component(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
set(REFERENCE_MODEL_DIR "${PORT_ROOT}/tools/reference_model")

add_library(portcore SHARED
    input_bridge.c
    "${REFERENCE_MODEL_DIR}/android_gamepad_adapter.c"
    "${REFERENCE_MODEL_DIR}/ps2_pad_report.c"
)

target_include_directories(portcore PRIVATE "${REFERENCE_MODEL_DIR}")
target_compile_options(portcore PRIVATE -Wall -Wextra -Werror -Wconversion -Wsign-conversion)
target_link_libraries(portcore android log)
