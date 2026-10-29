cmake_minimum_required(VERSION 3.22.1)
project(1945portcore LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

get_filename_component(PORT_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
set(REFERENCE_MODEL_DIR "${PORT_ROOT}/tools/reference_model")
set(GAME_DIR "${CMAKE_CURRENT_LIST_DIR}/game")

add_library(portcore SHARED
    input_bridge.c
    "${REFERENCE_MODEL_DIR}/android_gamepad_adapter.c"
    "${REFERENCE_MODEL_DIR}/ps2_pad_report.c"
    "${GAME_DIR}/game_core.c"
    "${GAME_DIR}/tim_image.c"
    "${GAME_DIR}/tim_texture_renderer.cpp"
    "${GAME_DIR}/audio_engine.c"
    "${GAME_DIR}/ps2_audio_control.c"
    "${GAME_DIR}/ps2_audio_sequence_catalog.c"
    "${GAME_DIR}/game_renderer.cpp"
    "${GAME_DIR}/game_bridge.cpp"
)

target_include_directories(portcore PRIVATE
    "${REFERENCE_MODEL_DIR}"
    "${GAME_DIR}"
)
target_compile_options(portcore PRIVATE
    -Wall -Wextra -Werror -Wconversion -Wsign-conversion
)
target_link_libraries(portcore android log GLESv2 m)
