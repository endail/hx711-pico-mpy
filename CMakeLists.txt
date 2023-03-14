# MIT License
# 
# Copyright (c) 2023 Daniel Robertson
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

set(CMAKE_VERBOSE_MAKEFILE ON)

cmake_minimum_required(VERSION 3.14)

set(CMAKE_C_STANDARD 11)

find_package(Python3
        COMPONENTS Interpreter
        )

#add_compile_options(
#        -Wall
#        -Wextra
#        -Werror
#        -Wfatal-errors
#        -Wfloat-equal
#        -Wunreachable-code
#        -Wno-unused-function
#        -Wno-maybe-uninitialized
#        -Wno-ignored-qualifiers
#        -Wno-stringop-overflow          # rp2040_usb.c:61:3
#        -Wno-array-bounds               # rp2040_usb.c:61:3
#        )

include(pico_sdk_import.cmake)

project(hx711-pico-mpy
        VERSION 0.0.1
        LANGUAGES C CXX ASM
        )

pico_sdk_init()

if(PICO_SDK_VERSION_STRING VERSION_LESS "1.5.0")
        message(FATAL_ERROR "hx711-pico-mpy requires Raspberry Pi Pico SDK version 1.5.0 (or later). Your version is ${PICO_SDK_VERSION_STRING}")
endif()

add_subdirectory(extern/hx711-pico-c)

add_library(${PROJECT_NAME} OBJECT
        )

target_link_libraries(${PROJECT_NAME}
        PUBLIC hx711-pico-c
        )

target_include_directories(${PROJECT_NAME}
        INTERFACE ${CMAKE_CURRENT_LIST_DIR}/extern/hx711-pico-c
        PRIVATE ${CMAKE_CURRENT_LIST_DIR}/extern/micropython
        )

target_sources(${PROJECT_NAME}
        INTERFACE
        ${CMAKE_CURRENT_LIST_DIR}/src/main.c
        )

add_custom_target(${PROJECT_NAME}_mpy_preprocessing
        ALL
        COMMAND Python3::Interpreter ${CMAKE_CURRENT_SOURCE_DIR}/extern/micropython/tools/mpy_ld.py -vvv --arch armv6m --preprocess -o ${CMAKE_CURRENT_BINARY_DIR}/hx711-pico-mpy.config.h ${CMAKE_CURRENT_LIST_DIR}/src/main.c
        COMMENT "MicroPython linker preprocessing..."
)

target_compile_options(${PROJECT_NAME}
        PUBLIC
        -std=c99
        -Os
#        -Wall
#        -Werror
        -DNDEBUG
        -DNO_QSTR
        -DMICROPY_ENABLE_DYNRUNTIME
        -DMP_CONFIGFILE="${CMAKE_CURRENT_BINARY_DIR}/hx711-pico-mpy.config.h"
        -fpic
        -fno-common
        -U _FORTIFY_SOURCE
        -mthumb
        -mcpu=cortex-m0
        -DHX711_NO_MUTEX
        )

add_dependencies(${PROJECT_NAME}
        ${PROJECT_NAME}_mpy_preprocessing
        )

add_custom_target(${PROJECT_NAME}_mpy_linking
        ALL
        COMMAND Python3::Interpreter ${CMAKE_CURRENT_SOURCE_DIR}/extern/micropython/tools/mpy_ld.py -vvv --arch armv6m --qstrs ${CMAKE_CURRENT_BINARY_DIR}/hx711-pico-mpy.config.h -o ${CMAKE_CURRENT_BINARY_DIR}/hx711-pico-mpy.native.mpy $<TARGET_OBJECTS:hx711-pico-mpy>
        COMMAND_EXPAND_LISTS
        COMMENT "MicroPython linking..."
)
