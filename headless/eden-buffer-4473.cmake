# SPDX-License-Identifier: GPL-3.0-or-later
# Selective, pinned upstream Eden #4473 backport for the native PS5 Vulkan path.
# https://github.com/eden-emulator/mirror/commit/dbeb73ee011416cffc6c203945f5ccc6b90621f6
# Do not change texture/buffer cache mutex ownership or GPU barriers.
# All replaces MUST match exactly once: abort on an unexpected Eden revision.
if(NOT PS5_NATIVE OR NOT EDEN_PS5_VULKAN)
    message(FATAL_ERROR "eden-buffer-4473.cmake: PS5 Vulkan only")
endif()

function(eden4473_replace variable old new)
    set(source "${${variable}}")
    string(REPLACE "${old}" "" no_anchor "${source}")
    string(LENGTH "${source}" before)
    string(LENGTH "${no_anchor}" after)
    string(LENGTH "${old}" anchor_length)
    if(anchor_length EQUAL 0)
        message(FATAL_ERROR "Eden #4473: empty replacement anchor")
    endif()
    math(EXPR occurrences "(${before} - ${after}) / ${anchor_length}")
    if(NOT occurrences EQUAL 1)
        message(FATAL_ERROR "Eden #4473: ${variable} pinned source mismatch, matches=${occurrences}")
    endif()
    string(REPLACE "${old}" "${new}" replaced "${source}")
    set(${variable} "${replaced}" PARENT_SCOPE)
endfunction()

set(eden4473_include "${PORT_BUILD_DIR}/eden4473")
file(MAKE_DIRECTORY "${eden4473_include}/video_core/buffer_cache"
                    "${eden4473_include}/video_core/engines")
file(READ "${PROJECT_SOURCE_DIR}/src/video_core/buffer_cache/buffer_cache.h" eden4473_buffer)
eden4473_replace(eden4473_buffer
    [=[void BufferCache<P>::WriteMemory(DAddr device_addr, u64 size) {
    if (memory_tracker.IsRegionGpuModified(device_addr, size)) {]=]
    [=[void BufferCache<P>::WriteMemory(DAddr device_addr, u64 size) {
    if (IsRegionGpuModified(device_addr, size)) {]=])
eden4473_replace(eden4473_buffer
    [=[    case ObtainBufferOperation::DiscardWrite: {
        const DAddr device_addr_start = Common::AlignDown(device_addr, 64);
        const DAddr device_addr_end = Common::AlignUp(device_addr + size, 64);
        const size_t new_size = device_addr_end - device_addr_start;
        ClearDownload(device_addr_start, new_size);
        gpu_modified_ranges.Subtract(device_addr_start, new_size);
        break;
    }]=]
    [=[    case ObtainBufferOperation::DiscardWrite: {
        ClearDownload(device_addr, size);
        gpu_modified_ranges.Subtract(device_addr, size);
        break;
    }]=])
eden4473_replace(eden4473_buffer
    [=[    memory_tracker.ForEachUploadRange(device_addr, size, [&](u64 device_addr_out, u64 range_size) {
        upload_copies.push_back(BufferCopy{
            .src_offset = total_size_bytes,
            .dst_offset = device_addr_out - buffer_start,
            .size = range_size,
        });
        total_size_bytes += range_size;
        largest_copy = (std::max)(largest_copy, range_size);
    });]=]
    [=[    const auto add_upload = [&](DAddr start, DAddr end) {
        if (start == end) return;
        const u64 range_size = end - start;
        upload_copies.push_back(BufferCopy{
            .src_offset = total_size_bytes,
            .dst_offset = start - buffer_start,
            .size = range_size,
        });
        total_size_bytes += range_size;
        largest_copy = (std::max)(largest_copy, range_size);
    };
    memory_tracker.ForEachUploadRange(device_addr, size, [&](u64 device_addr_out, u64 range_size) {
        DAddr upload_start = device_addr_out;
        gpu_modified_ranges.ForEachInRange(device_addr_out, range_size, [&](DAddr gpu_start, DAddr gpu_end) {
            add_upload(upload_start, gpu_start);
            upload_start = gpu_end;
        });
        add_upload(upload_start, device_addr_out + range_size);
    });]=])
write_derived("${eden4473_include}/video_core/buffer_cache/buffer_cache.h" "${eden4473_buffer}")

# PS5 uses a derived dma_pusher.cpp with shutdown-safe waits. Compose #4473
# on that DERIVED source when present, so the prior PS5 hang fixes survive.
if("${PORT_BUILD_DIR}/dma_pusher.cpp" IN_LIST video_sources)
    set(eden4473_dma_input "${PORT_BUILD_DIR}/dma_pusher.cpp")
else()
    set(eden4473_dma_input "${PROJECT_SOURCE_DIR}/src/video_core/dma_pusher.cpp")
endif()
file(READ "${eden4473_dma_input}" eden4473_dma)
eden4473_replace(eden4473_dma
    [=[[[maybe_unused]] constexpr u32 ComputeInline = 0x6D;]=]
    [=[constexpr u32 ComputeInline = 0x6D;]=])
eden4473_replace(eden4473_dma
    [=[    if (header.size > 0 && dma_state.method >= MacroRegistersStart && subchannels[dma_state.subchannel]) {
        subchannels[dma_state.subchannel]->current_dirty = memory_manager.IsMemoryDirty(dma_state.dma_get, header.size * sizeof(u32));
    }

    if (header.size > 0) {]=]
    [=[    if (header.size > 0) {
        if (subchannels[dma_state.subchannel] && dma_state.method_count) {
            const auto engine = subchannel_type[dma_state.subchannel];
            const bool kepler_payload = engine == Engines::EngineTypes::KeplerCompute && dma_state.method == ComputeInline && dma_state.non_incrementing;
            const bool macro_payload = engine == Engines::EngineTypes::Maxwell3D && dma_state.method >= MacroRegistersStart;
            if (kepler_payload || macro_payload) {
                const size_t words = std::min<size_t>(dma_state.method_count, header.size);
                subchannels[dma_state.subchannel]->current_dirty = memory_manager.IsMemoryDirty(dma_state.dma_get, words * sizeof(u32));
            }
        }]=])
write_derived("${PORT_BUILD_DIR}/eden4473/dma_pusher.cpp" "${eden4473_dma}")
list(REMOVE_ITEM video_sources "${PORT_BUILD_DIR}/dma_pusher.cpp" dma_pusher.cpp)
list(APPEND video_sources "${PORT_BUILD_DIR}/eden4473/dma_pusher.cpp")

file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/kepler_compute.h" eden4473_kepler_header)
eden4473_replace(eden4473_kepler_header
    [=[    GPUVAddr upload_address;

    struct UploadInfo {
        GPUVAddr upload_address;
        GPUVAddr exec_address;
        u32 copy_size;
    };]=]
    [=[    GPUVAddr upload_address;
    bool upload_dirty{};

    struct UploadInfo {
        GPUVAddr upload_address;
        GPUVAddr exec_address;
        u32 copy_size;
        bool was_dirty;
    };]=])
write_derived("${eden4473_include}/video_core/engines/kepler_compute.h" "${eden4473_kepler_header}")

file(READ "${PROJECT_SOURCE_DIR}/src/video_core/engines/kepler_compute.cpp" eden4473_kepler)
eden4473_replace(eden4473_kepler
    [=[                        .copy_size = upload_state.GetUploadSize()};]=]
    [=[                        .copy_size = upload_state.GetUploadSize(),
                        .was_dirty = upload_dirty};]=])
eden4473_replace(eden4473_kepler
    [=[        upload_address = current_dma_segment;
        upload_state.ProcessData(method_argument, is_last_call);]=]
    [=[        upload_address = current_dma_segment;
        upload_dirty = current_dirty;
        current_dirty = false;
        upload_state.ProcessData(method_argument, is_last_call);]=])
eden4473_replace(eden4473_kepler
    [=[            if (offset / sizeof(u32) == LAUNCH_REG_INDEX(grid_dim_x) &&
                memory_manager.IsMemoryDirty(data.upload_address, data.copy_size)) {
                indirect_compute = {data.upload_address};
            }]=]
    [=[            if (offset / sizeof(u32) == LAUNCH_REG_INDEX(grid_dim_x)) {
                const bool source_dirty = memory_manager.IsMemoryDirty(data.upload_address, data.copy_size);
                if (data.was_dirty || source_dirty) {
                    indirect_compute = {data.upload_address};
                }
            }]=])
eden4473_replace(eden4473_kepler
    [=[        upload_address = current_dma_segment;
        upload_state.ProcessData(base_start, amount);]=]
    [=[        upload_address = current_dma_segment;
        upload_dirty = current_dirty;
        current_dirty = false;
        upload_state.ProcessData(base_start, amount);]=])
write_derived("${PORT_BUILD_DIR}/eden4473/kepler_compute.cpp" "${eden4473_kepler}")
list(REMOVE_ITEM video_sources engines/kepler_compute.cpp)
list(APPEND video_sources "${PORT_BUILD_DIR}/eden4473/kepler_compute.cpp")

# Include the pinned header variants BEFORE the original upstream include root.
target_include_directories(video_core BEFORE PRIVATE "${eden4473_include}")
message(STATUS "Eden #4473 selective native Vulkan buffer/Kepler dirty tracking backport enabled")
