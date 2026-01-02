/**
 * VR Streamer - DXGI Desktop Duplication Capture Implementation
 * Optimized for maximum performance with minimal latency.
 */

#include "capture/dxgi_capture.hpp"
#include <dwmapi.h>
#include <algorithm>
#include <cstring>

#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "dxguid.lib")
#pragma comment(lib, "dwmapi.lib")

namespace vrs
{

    // ============================================================================
    // DXGICapture Implementation
    // ============================================================================

    DXGICapture::DXGICapture() = default;

    DXGICapture::~DXGICapture()
    {
        shutdown();
    }

    bool DXGICapture::init(u32 monitor_index)
    {
        shutdown();

        monitor_index_ = monitor_index;
        target_window_ = nullptr;

        if (!create_device())
        {
            VRS_LOG_ERROR("Failed to create D3D11 device");
            return false;
        }

        if (!create_duplication(monitor_index))
        {
            VRS_LOG_ERROR("Failed to create output duplication");
            return false;
        }

        if (!create_staging_texture())
        {
            VRS_LOG_ERROR("Failed to create staging texture");
            return false;
        }

        initialized_ = true;
        frame_id_ = 0;

        VRS_LOG_INFO(std::format("DXGI capture initialized: {}x{} @ monitor {}",
                                 width_, height_, monitor_index));

        return true;
    }

    bool DXGICapture::init_window(HWND hwnd)
    {
        if (!IsWindow(hwnd))
        {
            VRS_LOG_ERROR("Invalid window handle");
            return false;
        }

        // Get the monitor this window is on
        HMONITOR monitor = MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST);

        // Find monitor index
        auto monitors = enumerate_monitors();
        u32 monitor_index = 0;
        for (size_t i = 0; i < monitors.size(); ++i)
        {
            if (monitors[i].handle == monitor)
            {
                monitor_index = static_cast<u32>(i);
                break;
            }
        }

        if (!init(monitor_index))
        {
            return false;
        }

        target_window_ = hwnd;

        // Get initial window rect
        RECT rect;
        DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &rect, sizeof(rect));
        window_rect_ = rect;

        VRS_LOG_INFO(std::format("Window capture initialized: HWND={}, rect=({},{},{},{}), monitor rect=({},{},{},{})",
                                 reinterpret_cast<uintptr_t>(hwnd),
                                 rect.left, rect.top, rect.right, rect.bottom,
                                 monitor_rect_.left, monitor_rect_.top, monitor_rect_.right, monitor_rect_.bottom));

        return true;
    }

    void DXGICapture::shutdown()
    {
        if (duplication_)
        {
            duplication_->ReleaseFrame();
        }

        staging_texture_ = nullptr;
        duplication_ = nullptr;
        output_ = nullptr;
        adapter_ = nullptr;
        context_ = nullptr;
        device_ = nullptr;

        initialized_ = false;
        width_ = 0;
        height_ = 0;
    }

    bool DXGICapture::create_device()
    {
        UINT flags = D3D11_CREATE_DEVICE_BGRA_SUPPORT;

#ifndef NDEBUG
        flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

        D3D_FEATURE_LEVEL feature_levels[] = {
            D3D_FEATURE_LEVEL_11_1,
            D3D_FEATURE_LEVEL_11_0,
            D3D_FEATURE_LEVEL_10_1,
            D3D_FEATURE_LEVEL_10_0};

        D3D_FEATURE_LEVEL feature_level;

        ID3D11Device *device = nullptr;
        ID3D11DeviceContext *context = nullptr;

        // Try to create device with hardware adapter
        HRESULT hr = D3D11CreateDevice(
            nullptr, // Use default adapter
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            flags,
            feature_levels,
            _countof(feature_levels),
            D3D11_SDK_VERSION,
            &device,
            &feature_level,
            &context);

        if (FAILED(hr))
        {
            VRS_LOG_WARN("Hardware D3D11 device creation failed, trying WARP");

            hr = D3D11CreateDevice(
                nullptr,
                D3D_DRIVER_TYPE_WARP,
                nullptr,
                flags,
                feature_levels,
                _countof(feature_levels),
                D3D11_SDK_VERSION,
                &device,
                &feature_level,
                &context);

            if (FAILED(hr))
            {
                return false;
            }
        }

        device_.reset(device);
        context_.reset(context);

        // Set multithread protection
        ComPtr<ID3D10Multithread> multithread;
        hr = device_->QueryInterface(__uuidof(ID3D10Multithread),
                                     reinterpret_cast<void **>(multithread.address_of()));
        if (SUCCEEDED(hr))
        {
            multithread->SetMultithreadProtected(TRUE);
        }

        return true;
    }

    bool DXGICapture::create_duplication(u32 monitor_index)
    {
        // Get DXGI device
        ComPtr<IDXGIDevice1> dxgi_device;
        HRESULT hr = device_->QueryInterface(__uuidof(IDXGIDevice1),
                                             reinterpret_cast<void **>(dxgi_device.address_of()));
        if (FAILED(hr))
        {
            return false;
        }

        // Get adapter
        IDXGIAdapter *adapter = nullptr;
        hr = dxgi_device->GetAdapter(&adapter);
        if (FAILED(hr))
        {
            return false;
        }

        hr = adapter->QueryInterface(__uuidof(IDXGIAdapter1),
                                     reinterpret_cast<void **>(adapter_.address_of()));
        adapter->Release();
        if (FAILED(hr))
        {
            return false;
        }

        // Get output
        ComPtr<IDXGIOutput> output;
        hr = adapter_->EnumOutputs(monitor_index, output.address_of());
        if (FAILED(hr))
        {
            VRS_LOG_ERROR(std::format("Monitor {} not found", monitor_index));
            return false;
        }

        hr = output->QueryInterface(__uuidof(IDXGIOutput1),
                                    reinterpret_cast<void **>(output_.address_of()));
        if (FAILED(hr))
        {
            return false;
        }

        // Get output description for dimensions
        DXGI_OUTPUT_DESC desc;
        output_->GetDesc(&desc);
        width_ = desc.DesktopCoordinates.right - desc.DesktopCoordinates.left;
        height_ = desc.DesktopCoordinates.bottom - desc.DesktopCoordinates.top;

        // Store monitor rect for window clipping calculations
        monitor_rect_ = desc.DesktopCoordinates;

        // Create output duplication
        IDXGIOutputDuplication *duplication = nullptr;
        hr = output_->DuplicateOutput(device_.get(), &duplication);
        if (FAILED(hr))
        {
            if (hr == DXGI_ERROR_NOT_CURRENTLY_AVAILABLE)
            {
                VRS_LOG_ERROR("Desktop duplication not available - another app may be using it");
            }
            else if (hr == E_ACCESSDENIED)
            {
                VRS_LOG_ERROR("Access denied - running in a session without desktop access?");
            }
            else
            {
                VRS_LOG_ERROR(std::format("DuplicateOutput failed: {:08X}", static_cast<u32>(hr)));
            }
            return false;
        }

        duplication_.reset(duplication);
        return true;
    }

    bool DXGICapture::create_staging_texture()
    {
        D3D11_TEXTURE2D_DESC desc = {};
        desc.Width = width_;
        desc.Height = height_;
        desc.MipLevels = 1;
        desc.ArraySize = 1;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count = 1;
        desc.SampleDesc.Quality = 0;
        desc.Usage = D3D11_USAGE_STAGING;
        desc.BindFlags = 0;
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
        desc.MiscFlags = 0;

        ID3D11Texture2D *staging = nullptr;
        HRESULT hr = device_->CreateTexture2D(&desc, nullptr, &staging);
        if (FAILED(hr))
        {
            return false;
        }

        staging_texture_.reset(staging);
        return true;
    }

    bool DXGICapture::reinit_duplication()
    {
        if (duplication_)
        {
            duplication_->ReleaseFrame();
            duplication_ = nullptr;
        }

        // Wait a bit for resources to be released
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        return create_duplication(monitor_index_);
    }

    bool DXGICapture::capture_frame(CapturedFrame &frame, u32 timeout_ms)
    {
        if (!initialized_ || !duplication_)
        {
            return false;
        }

        Timer timer;

        IDXGIResource *resource = nullptr;
        DXGI_OUTDUPL_FRAME_INFO frame_info = {};

        HRESULT hr = duplication_->AcquireNextFrame(timeout_ms, &frame_info, &resource);

        if (hr == DXGI_ERROR_WAIT_TIMEOUT)
        {
            // No new frame available - not an error
            return false;
        }

        if (hr == DXGI_ERROR_ACCESS_LOST)
        {
            VRS_LOG_WARN("Desktop duplication access lost, reinitializing");
            if (!reinit_duplication())
            {
                return false;
            }
            return false; // Try again next frame
        }

        if (FAILED(hr))
        {
            stats_.frames_dropped++;
            return false;
        }

        // Get texture from resource
        ID3D11Texture2D *tex = nullptr;
        hr = resource->QueryInterface(__uuidof(ID3D11Texture2D), reinterpret_cast<void **>(&tex));
        resource->Release();

        if (FAILED(hr))
        {
            duplication_->ReleaseFrame();
            return false;
        }

        // Fill frame data
        frame.gpu_texture.reset(tex);
        frame.width = width_;
        frame.height = height_;
        frame.timestamp = std::chrono::duration_cast<Nanoseconds>(
                              Clock::now().time_since_epoch())
                              .count();
        frame.frame_id = ++frame_id_;

        // Cursor info
        if (frame_info.PointerPosition.Visible)
        {
            frame.cursor_visible = true;
            frame.cursor_x = frame_info.PointerPosition.Position.x;
            frame.cursor_y = frame_info.PointerPosition.Position.y;
        }
        else
        {
            frame.cursor_visible = false;
        }

        stats_.frames_captured++;
        fps_counter_.tick();
        fps_ = fps_counter_.fps();

        // Update timing stats
        capture_time_accum_ += timer.elapsed_ms();
        if (++time_sample_count_ >= 60)
        {
            stats_.avg_capture_time_ms = capture_time_accum_ / time_sample_count_;
            capture_time_accum_ = 0;
            time_sample_count_ = 0;
        }

        return true;
    }

    bool DXGICapture::update_window_rect()
    {
        if (!target_window_ || !IsWindow(target_window_))
        {
            return false;
        }

        // Get current window rect using DWM for accurate bounds
        RECT rect;
        HRESULT hr = DwmGetWindowAttribute(target_window_, DWMWA_EXTENDED_FRAME_BOUNDS, &rect, sizeof(rect));
        if (FAILED(hr))
        {
            if (!GetWindowRect(target_window_, &rect))
            {
                return false;
            }
        }

        window_rect_ = rect;
        return true;
    }

    bool DXGICapture::clip_to_window(CapturedFrame &frame)
    {
        if (!target_window_)
        {
            return true; // No window target, nothing to clip
        }

        // Update window position (windows can move)
        if (!update_window_rect())
        {
            VRS_LOG_WARN("Window no longer valid");
            return false;
        }

        // Calculate window position relative to monitor
        i32 win_left = window_rect_.left - monitor_rect_.left;
        i32 win_top = window_rect_.top - monitor_rect_.top;
        i32 win_right = window_rect_.right - monitor_rect_.left;
        i32 win_bottom = window_rect_.bottom - monitor_rect_.top;

        // Log clipping info (only once per second to avoid spam)
        static u64 last_log_time = 0;
        u64 now = std::chrono::duration_cast<std::chrono::seconds>(
                      Clock::now().time_since_epoch())
                      .count();
        if (now != last_log_time)
        {
            last_log_time = now;
            VRS_LOG_DEBUG(std::format("Clipping window: win_rect=({},{},{},{}), mon_rect=({},{},{},{}), rel=({},{},{},{})",
                                      window_rect_.left, window_rect_.top, window_rect_.right, window_rect_.bottom,
                                      monitor_rect_.left, monitor_rect_.top, monitor_rect_.right, monitor_rect_.bottom,
                                      win_left, win_top, win_right, win_bottom));
        }

        // Clamp to monitor bounds
        win_left = std::max(0, win_left);
        win_top = std::max(0, win_top);
        win_right = std::min(static_cast<i32>(width_), win_right);
        win_bottom = std::min(static_cast<i32>(height_), win_bottom);

        // Calculate clipped dimensions
        clipped_width_ = static_cast<u32>(win_right - win_left);
        clipped_height_ = static_cast<u32>(win_bottom - win_top);

        // Ensure valid dimensions
        if (clipped_width_ < 10 || clipped_height_ < 10)
        {
            VRS_LOG_WARN("Window too small or off-screen");
            return false;
        }

        // Allocate buffer for clipped data (4 bytes per pixel for BGRA)
        size_t clipped_pitch = clipped_width_ * 4;
        size_t clipped_size = clipped_pitch * clipped_height_;

        if (clipped_buffer_.size() < clipped_size)
        {
            clipped_buffer_.resize(clipped_size);
        }

        // Copy clipped region row by row
        const u8 *src = frame.cpu_data;
        u8 *dst = clipped_buffer_.data();

        for (u32 y = 0; y < clipped_height_; ++y)
        {
            const u8 *src_row = src + (win_top + y) * frame.pitch + win_left * 4;
            u8 *dst_row = dst + y * clipped_pitch;
            std::memcpy(dst_row, src_row, clipped_width_ * 4);
        }

        // Update frame to point to clipped data
        frame.cpu_data = clipped_buffer_.data();
        frame.width = clipped_width_;
        frame.height = clipped_height_;
        frame.pitch = static_cast<u32>(clipped_pitch);

        return true;
    }

    bool DXGICapture::copy_to_cpu(CapturedFrame &frame)
    {
        if (!frame.gpu_texture || !staging_texture_)
        {
            return false;
        }

        Timer timer;

        // Copy GPU texture to staging texture
        context_->CopyResource(staging_texture_.get(), frame.gpu_texture.get());

        // Map staging texture to CPU memory
        D3D11_MAPPED_SUBRESOURCE mapped;
        HRESULT hr = context_->Map(staging_texture_.get(), 0, D3D11_MAP_READ, 0, &mapped);
        if (FAILED(hr))
        {
            return false;
        }

        frame.cpu_data = static_cast<u8 *>(mapped.pData);
        frame.pitch = mapped.RowPitch;
        frame.staging_texture = staging_texture_;

        // If window capture, clip to window region
        if (target_window_)
        {
            if (!clip_to_window(frame))
            {
                context_->Unmap(staging_texture_.get(), 0);
                frame.cpu_data = nullptr;
                return false;
            }
        }

        copy_time_accum_ += timer.elapsed_ms();
        stats_.avg_copy_time_ms = copy_time_accum_ / (stats_.frames_captured > 0 ? stats_.frames_captured : 1);

        return true;
    }

    void DXGICapture::release_frame(CapturedFrame &frame)
    {
        // Unmap staging texture if it was mapped
        if (frame.cpu_data && frame.staging_texture)
        {
            context_->Unmap(frame.staging_texture.get(), 0);
            frame.cpu_data = nullptr;
        }

        // Release GPU texture
        frame.gpu_texture = nullptr;
        frame.staging_texture = nullptr;

        // Release the acquired frame from duplication
        if (duplication_)
        {
            duplication_->ReleaseFrame();
        }
    }

    std::vector<MonitorInfo> DXGICapture::enumerate_monitors()
    {
        std::vector<MonitorInfo> monitors;

        ComPtr<IDXGIFactory1> factory;
        HRESULT hr = CreateDXGIFactory1(__uuidof(IDXGIFactory1),
                                        reinterpret_cast<void **>(factory.address_of()));
        if (FAILED(hr))
        {
            return monitors;
        }

        ComPtr<IDXGIAdapter1> adapter;
        for (UINT adapter_idx = 0;
             factory->EnumAdapters1(adapter_idx, adapter.address_of()) != DXGI_ERROR_NOT_FOUND;
             ++adapter_idx)
        {

            ComPtr<IDXGIOutput> output;
            for (UINT output_idx = 0;
                 adapter->EnumOutputs(output_idx, output.address_of()) != DXGI_ERROR_NOT_FOUND;
                 ++output_idx)
            {

                DXGI_OUTPUT_DESC desc;
                output->GetDesc(&desc);

                MonitorInfo info;
                info.index = static_cast<u32>(monitors.size());
                info.name = desc.DeviceName;
                info.left = desc.DesktopCoordinates.left;
                info.top = desc.DesktopCoordinates.top;
                info.right = desc.DesktopCoordinates.right;
                info.bottom = desc.DesktopCoordinates.bottom;
                info.handle = desc.Monitor;

                // Check if primary
                MONITORINFO mi;
                mi.cbSize = sizeof(mi);
                GetMonitorInfoW(desc.Monitor, &mi);
                info.is_primary = (mi.dwFlags & MONITORINFOF_PRIMARY) != 0;

                monitors.push_back(info);
                output = nullptr;
            }
            adapter = nullptr;
        }

        return monitors;
    }

    std::vector<WindowInfo> DXGICapture::enumerate_windows()
    {
        std::vector<WindowInfo> windows;

        auto enum_callback = [](HWND hwnd, LPARAM lparam) -> BOOL
        {
            auto *list = reinterpret_cast<std::vector<WindowInfo> *>(lparam);

            // Check if window is visible
            if (!IsWindowVisible(hwnd))
            {
                return TRUE;
            }

            // Get window title
            wchar_t title[512];
            int title_len = GetWindowTextW(hwnd, title, 512);
            if (title_len == 0)
            {
                return TRUE;
            }

            // Get window style
            LONG style = GetWindowLong(hwnd, GWL_STYLE);
            LONG ex_style = GetWindowLong(hwnd, GWL_EXSTYLE);

            // Skip tool windows without app window style
            if ((ex_style & WS_EX_TOOLWINDOW) && !(ex_style & WS_EX_APPWINDOW))
            {
                return TRUE;
            }

            // Get window rect
            RECT rect;
            if (DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &rect, sizeof(rect)) != S_OK)
            {
                if (!GetWindowRect(hwnd, &rect))
                {
                    return TRUE;
                }
            }

            // Skip tiny windows
            int width = rect.right - rect.left;
            int height = rect.bottom - rect.top;
            if (width < 100 || height < 100)
            {
                return TRUE;
            }

            // Get class name
            wchar_t class_name[256];
            GetClassNameW(hwnd, class_name, 256);

            // Skip certain system windows
            std::wstring_view class_view(class_name);
            if (class_view == L"Progman" || class_view == L"WorkerW" ||
                class_view == L"Shell_TrayWnd" || class_view == L"Windows.UI.Core.CoreWindow")
            {
                return TRUE;
            }

            // Check if cloaked
            BOOL cloaked = FALSE;
            DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, &cloaked, sizeof(cloaked));
            if (cloaked)
            {
                return TRUE;
            }

            WindowInfo info;
            info.hwnd = hwnd;
            info.title = title;
            info.class_name = class_name;
            info.left = rect.left;
            info.top = rect.top;
            info.right = rect.right;
            info.bottom = rect.bottom;
            info.is_visible = true;

            GetWindowThreadProcessId(hwnd, &info.process_id);

            list->push_back(info);
            return TRUE;
        };

        EnumWindows(enum_callback, reinterpret_cast<LPARAM>(&windows));

        // Sort by title
        std::sort(windows.begin(), windows.end(), [](const WindowInfo &a, const WindowInfo &b)
                  { return a.title < b.title; });

        return windows;
    }

    // ============================================================================
    // CaptureManager Implementation
    // ============================================================================

    CaptureManager::CaptureManager() = default;
    CaptureManager::~CaptureManager() = default;

    bool CaptureManager::init()
    {
        return capture_.init(0);
    }

    bool CaptureManager::set_monitor(u32 monitor_index)
    {
        use_window_capture_ = false;
        selected_window_ = {};
        return capture_.init(monitor_index);
    }

    bool CaptureManager::set_window(HWND hwnd)
    {
        use_window_capture_ = true;

        // Get window info
        wchar_t title[512];
        GetWindowTextW(hwnd, title, 512);

        wchar_t class_name[256];
        GetClassNameW(hwnd, class_name, 256);

        RECT rect;
        DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, &rect, sizeof(rect));

        selected_window_.hwnd = hwnd;
        selected_window_.title = title;
        selected_window_.class_name = class_name;
        selected_window_.left = rect.left;
        selected_window_.top = rect.top;
        selected_window_.right = rect.right;
        selected_window_.bottom = rect.bottom;
        selected_window_.is_visible = true;

        return capture_.init_window(hwnd);
    }

    bool CaptureManager::set_window_by_title(std::wstring_view title)
    {
        auto windows = DXGICapture::enumerate_windows();

        for (const auto &win : windows)
        {
            if (win.title.find(title) != std::wstring::npos)
            {
                return set_window(win.hwnd);
            }
        }

        return false;
    }

    bool CaptureManager::capture(CapturedFrame &frame, u32 timeout_ms)
    {
        if (!capture_.initialized())
        {
            // Try to recover
            if (recovery_attempts_ >= MAX_RECOVERY_ATTEMPTS)
            {
                return false;
            }

            recovery_attempts_++;
            if (use_window_capture_ && selected_window_.hwnd)
            {
                if (!capture_.init_window(selected_window_.hwnd))
                {
                    return false;
                }
            }
            else
            {
                if (!capture_.init(0))
                {
                    return false;
                }
            }
            recovery_attempts_ = 0;
        }

        return capture_.capture_frame(frame, timeout_ms);
    }

    bool CaptureManager::copy_to_cpu(CapturedFrame &frame)
    {
        return capture_.copy_to_cpu(frame);
    }

    void CaptureManager::release_frame(CapturedFrame &frame)
    {
        capture_.release_frame(frame);
    }

    std::vector<WindowInfo> CaptureManager::refresh_windows()
    {
        return DXGICapture::enumerate_windows();
    }

    // ============================================================================
    // Logging Implementation
    // ============================================================================

    namespace
    {
        std::mutex log_mutex;
    }

    void log_debug(std::string_view msg)
    {
        std::lock_guard lock(log_mutex);
        printf("[DEBUG] %.*s\n", static_cast<int>(msg.size()), msg.data());
    }

    void log_info(std::string_view msg)
    {
        std::lock_guard lock(log_mutex);
        printf("[INFO] %.*s\n", static_cast<int>(msg.size()), msg.data());
    }

    void log_warn(std::string_view msg)
    {
        std::lock_guard lock(log_mutex);
        printf("[WARN] %.*s\n", static_cast<int>(msg.size()), msg.data());
    }

    void log_error(std::string_view msg)
    {
        std::lock_guard lock(log_mutex);
        fprintf(stderr, "[ERROR] %.*s\n", static_cast<int>(msg.size()), msg.data());
    }

} // namespace vrs
