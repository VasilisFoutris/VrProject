cmake_minimum_required(VERSION 3.20)

# Make CUDA optional
option(ENABLE_CUDA "Enable CUDA acceleration" OFF)

if(ENABLE_CUDA)
    project(VRStreamer VERSION 1.0.0 LANGUAGES CXX CUDA)
    set(CMAKE_CUDA_STANDARD 17)
    set(CMAKE_CUDA_STANDARD_REQUIRED ON)
else()
    project(VRStreamer VERSION 1.0.0 LANGUAGES CXX)
endif()

# C++20 for maximum modern features
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# Build type
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler-specific optimizations
if(MSVC)
    add_compile_options(
        /W4                     # Warning level 4
        /MP                     # Multi-processor compilation
        /fp:fast                # Fast floating point
        /Oi                     # Enable intrinsic functions
        /Ot                     # Favor fast code
        /permissive-            # Standards conformance
        /Zc:__cplusplus         # Correct __cplusplus macro
        /EHsc                   # Exception handling
    )
    
    # Only add AVX2 for Release builds (may crash on older CPUs)
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
        add_compile_options(/O2 /arch:AVX2 /GL /GS-)
        add_link_options(/LTCG /OPT:REF /OPT:ICF)
    endif()
else()
    add_compile_options(
        -Wall -Wextra -Wpedantic
        -O3
        -ffast-math
        -funroll-loops
    )
    if(CMAKE_BUILD_TYPE STREQUAL "Release")
        add_compile_options(-march=native -flto)
    endif()
endif()

# CUDA optimizations (if enabled)
if(ENABLE_CUDA)
    find_package(CUDAToolkit REQUIRED)
    set(CMAKE_CUDA_FLAGS "${CMAKE_CUDA_FLAGS} -O3 --use_fast_math")
    add_compile_definitions(HAS_CUDA=1)
endif()

# Find packages via vcpkg
find_package(Boost 1.80 REQUIRED COMPONENTS system)
find_package(libjpeg-turbo CONFIG REQUIRED)

# Source files (excluding CUDA files when disabled)
set(SOURCES
    src/main.cpp
    src/capture/dxgi_capture.cpp
    src/encoder/jpeg_encoder.cpp
    src/encoder/stereo_processor.cpp
    src/network/websocket_server.cpp
    src/network/http_server.cpp
    src/core/config.cpp
    src/core/vr_streamer_app.cpp
)

# Add CUDA sources if enabled
if(ENABLE_CUDA)
    list(APPEND SOURCES
        src/encoder/stereo_processor.cu
    )
endif()

set(HEADERS
    include/vr_streamer.hpp
    include/capture/dxgi_capture.hpp
    include/encoder/jpeg_encoder.hpp
    include/encoder/stereo_processor.hpp
    include/network/websocket_server.hpp
    include/network/http_server.hpp
    include/core/config.hpp
    include/core/memory_pool.hpp
    include/core/thread_pool.hpp
    include/core/spsc_queue.hpp
    include/core/common.hpp
)

# Main executable
add_executable(vr_streamer ${SOURCES} ${HEADERS})

target_include_directories(vr_streamer PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
    ${Boost_INCLUDE_DIRS}
)

# Link libraries
target_link_libraries(vr_streamer PRIVATE
    # Windows system libraries
    d3d11
    dxgi
    dxguid
    dwmapi
    user32
    ws2_32
    mswsock
    
    # Boost
    Boost::system
    
    # TurboJPEG (from vcpkg)
    $<IF:$<TARGET_EXISTS:libjpeg-turbo::turbojpeg>,libjpeg-turbo::turbojpeg,libjpeg-turbo::turbojpeg-static>
)

# CUDA libraries (if enabled)
if(ENABLE_CUDA)
    target_include_directories(vr_streamer PRIVATE ${CUDAToolkit_INCLUDE_DIRS})
    target_link_libraries(vr_streamer PRIVATE
        CUDA::cudart
        CUDA::cuda_driver
        CUDA::nvjpeg
    )
endif()

# Suppress warnings from Boost headers
target_compile_options(vr_streamer PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/wd4244 /wd4267 /wd4996>
)

# Install rules
install(TARGETS vr_streamer RUNTIME DESTINATION bin)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/../mobile_app/ DESTINATION share/mobile_app)
