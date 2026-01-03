/**
 * VR Streamer - Main Entry Point
 * High-performance VR streaming application.
 */

#include "vr_streamer.hpp"
#include <iostream>
#include <csignal>
#include <cstdio>
#include <conio.h>

using namespace vrs;

// Global application pointer for signal handling
static VRStreamerApp *g_app = nullptr;

void signal_handler(int signal)
{
    if (g_app)
    {
        std::cout << "\nShutting down...\n";
        g_app->stop();
    }
}

void print_banner()
{
    std::cout << R"(
╔═══════════════════════════════════════════════════════════╗
║              VR Screen Streamer v1.0 (C++)                ║
║         High-Performance GPU-Accelerated Edition          ║
╚═══════════════════════════════════════════════════════════╝
)" << std::endl;
}

void print_stats(const PipelineStats &stats)
{
    std::cout << "Capture: " << std::fixed << std::setprecision(1) << stats.capture_fps << " fps | "
              << "Encode: " << stats.encode_fps << " fps | "
              << "Stream: " << stats.stream_fps << " fps | "
              << "Clients: " << stats.connected_clients << " | "
              << "Bitrate: " << std::setprecision(2) << stats.bitrate_mbps << " Mbps | "
              << "Quality: " << stats.current_quality
              << std::endl;
}

void print_help()
{
    std::cout << R"(
Usage: vr_streamer [options]

Options:
  -h, --help          Show this help message
  -p, --port <port>   WebSocket port (default: 8765)
  -q, --quality <q>   JPEG quality 1-100 (default: 65)
  -f, --fps <fps>     Target FPS (default: 60)
  -s, --scale <s>     Downscale factor 0.1-1.0 (default: 0.65)
  -m, --monitor <n>   Monitor index (default: 0)
  --hwnd <handle>     Capture specific window by handle
  --preset <name>     Quality preset: ultra_performance, low_latency,
                      balanced, quality, maximum_quality
  --no-vr             Disable VR stereo mode
  --no-gpu            Disable GPU acceleration

Controls (during streaming):
  Q         - Quit
  +/-       - Increase/decrease quality
  [/]       - Increase/decrease downscale
  1-5       - Apply quality preset
  W         - List windows
  R         - Refresh window list

)" << std::endl;
}

int main(int argc, char *argv[])
{
    // Disable stdout buffering for immediate output when piped to GUI
    setvbuf(stdout, nullptr, _IONBF, 0);
    setvbuf(stderr, nullptr, _IONBF, 0);
    
    print_banner();

    // Parse command line arguments
    Config config = Config::default_config();
    bool show_help = false;
    HWND target_hwnd = nullptr; // Window handle for window capture

    for (int i = 1; i < argc; ++i)
    {
        std::string arg = argv[i];

        if (arg == "-h" || arg == "--help")
        {
            show_help = true;
        }
        else if ((arg == "-p" || arg == "--port") && i + 1 < argc)
        {
            config.network.port = static_cast<u16>(std::stoi(argv[++i]));
        }
        else if ((arg == "-q" || arg == "--quality") && i + 1 < argc)
        {
            config.encoder.jpeg_quality = std::clamp(std::stoi(argv[++i]), 1, 100);
        }
        else if ((arg == "-f" || arg == "--fps") && i + 1 < argc)
        {
            config.capture.target_fps = std::clamp(std::stoi(argv[++i]), 1, 240);
        }
        else if ((arg == "-s" || arg == "--scale") && i + 1 < argc)
        {
            config.encoder.downscale_factor = std::clamp(std::stof(argv[++i]), 0.1f, 1.0f);
        }
        else if ((arg == "-m" || arg == "--monitor") && i + 1 < argc)
        {
            config.capture.monitor_index = std::stoi(argv[++i]);
        }
        else if (arg == "--hwnd" && i + 1 < argc)
        {
            // Parse window handle as unsigned integer
            target_hwnd = reinterpret_cast<HWND>(static_cast<uintptr_t>(std::stoull(argv[++i])));
        }
        else if (arg == "--preset" && i + 1 < argc)
        {
            std::string preset = argv[++i];
            if (preset == "ultra_performance")
                config.apply_preset(QualityPreset::ULTRA_PERFORMANCE);
            else if (preset == "low_latency")
                config.apply_preset(QualityPreset::LOW_LATENCY);
            else if (preset == "balanced")
                config.apply_preset(QualityPreset::BALANCED);
            else if (preset == "quality")
                config.apply_preset(QualityPreset::QUALITY);
            else if (preset == "maximum_quality")
                config.apply_preset(QualityPreset::MAXIMUM_QUALITY);
        }
        else if (arg == "--no-vr")
        {
            config.encoder.vr_enabled = false;
        }
        else if (arg == "--no-gpu")
        {
            config.encoder.use_gpu = false;
            config.encoder.use_nvenc = false;
            config.encoder.use_nvjpeg = false;
        }
    }

    if (show_help)
    {
        print_help();
        return 0;
    }

    // Create application
    VRStreamerApp app;
    g_app = &app;

    // Setup signal handler
    std::signal(SIGINT, signal_handler);
    std::signal(SIGTERM, signal_handler);

    // Initialize
    std::cout << "Initializing...\n"
              << std::endl;

    if (!app.init(config))
    {
        std::cerr << "Failed to initialize application" << std::endl;
        return 1;
    }

    // Print configuration
    std::cout << "Configuration:\n"
              << "  Target FPS: " << config.capture.target_fps << "\n"
              << "  Quality: " << config.encoder.jpeg_quality << "\n"
              << "  Downscale: " << config.encoder.downscale_factor << "\n"
              << "  VR Mode: " << (config.encoder.vr_enabled ? "Enabled" : "Disabled") << "\n"
              << "  GPU Accel: " << (config.encoder.use_gpu ? "Enabled" : "Disabled") << "\n"
              << std::endl;

    // List available monitors
    auto monitors = app.get_monitors();
    std::cout << "Available monitors:\n";
    for (const auto &mon : monitors)
    {
        std::wcout << L"  " << mon.index << L": " << mon.name
                   << L" (" << mon.width() << L"x" << mon.height() << L")"
                   << (mon.is_primary ? L" [Primary]" : L"") << L"\n";
    }
    std::cout << std::endl;

    // Set window capture if specified
    if (target_hwnd != nullptr)
    {
        if (IsWindow(target_hwnd))
        {
            wchar_t title[256] = {0};
            GetWindowTextW(target_hwnd, title, 256);
            std::wcout << L"Capturing window: " << title << L" (HWND: " << target_hwnd << L")\n"
                       << std::endl;
            app.set_capture_window(target_hwnd);
        }
        else
        {
            std::cout << "Warning: Invalid window handle " << target_hwnd << ", using monitor capture\n"
                      << std::endl;
        }
    }

    // Set stats callback
    app.set_on_stats_update([](const PipelineStats &stats)
                            { print_stats(stats); });

    // Set client callbacks
    app.set_on_client_connect([](const ClientInfo &client)
                              { std::cout << "\n[+] Client connected: " << client.address << std::endl; });

    app.set_on_client_disconnect([](const ClientInfo &client)
                                 { std::cout << "\n[-] Client disconnected: " << client.address << std::endl; });

    // Start streaming
    if (!app.start())
    {
        std::cerr << "Failed to start streaming" << std::endl;
        return 1;
    }

    std::cout << "Server running at: " << app.connection_url() << "\n"
              << "Press 'Q' to quit, 'H' for help\n"
              << std::endl;

    // Main control loop
    while (app.streaming())
    {
        if (_kbhit())
        {
            int key = _getch();

            switch (std::tolower(key))
            {
            case 'q':
                app.stop();
                break;

            case 'h':
                std::cout << "\n\nControls:\n"
                          << "  Q - Quit\n"
                          << "  +/- - Quality up/down\n"
                          << "  [/] - Scale up/down\n"
                          << "  1-5 - Presets\n"
                          << "  W - List windows\n"
                          << std::endl;
                break;

            case '+':
            case '=':
            {
                auto cfg = app.config();
                cfg.encoder.jpeg_quality = std::min(100u, cfg.encoder.jpeg_quality + 5);
                app.update_config(cfg);
                std::cout << "\nQuality: " << cfg.encoder.jpeg_quality << std::endl;
            }
            break;

            case '-':
            case '_':
            {
                auto cfg = app.config();
                cfg.encoder.jpeg_quality = std::max(10u, cfg.encoder.jpeg_quality - 5);
                app.update_config(cfg);
                std::cout << "\nQuality: " << cfg.encoder.jpeg_quality << std::endl;
            }
            break;

            case ']':
            {
                auto cfg = app.config();
                cfg.encoder.downscale_factor = std::min(1.0f, cfg.encoder.downscale_factor + 0.05f);
                app.update_config(cfg);
                std::cout << "\nScale: " << cfg.encoder.downscale_factor << std::endl;
            }
            break;

            case '[':
            {
                auto cfg = app.config();
                cfg.encoder.downscale_factor = std::max(0.2f, cfg.encoder.downscale_factor - 0.05f);
                app.update_config(cfg);
                std::cout << "\nScale: " << cfg.encoder.downscale_factor << std::endl;
            }
            break;

            case '1':
                app.set_quality_preset(QualityPreset::ULTRA_PERFORMANCE);
                std::cout << "\nPreset: Ultra Performance" << std::endl;
                break;

            case '2':
                app.set_quality_preset(QualityPreset::LOW_LATENCY);
                std::cout << "\nPreset: Low Latency" << std::endl;
                break;

            case '3':
                app.set_quality_preset(QualityPreset::BALANCED);
                std::cout << "\nPreset: Balanced" << std::endl;
                break;

            case '4':
                app.set_quality_preset(QualityPreset::QUALITY);
                std::cout << "\nPreset: Quality" << std::endl;
                break;

            case '5':
                app.set_quality_preset(QualityPreset::MAXIMUM_QUALITY);
                std::cout << "\nPreset: Maximum Quality" << std::endl;
                break;

            case 'w':
            {
                std::cout << "\n\nAvailable windows:\n";
                auto windows = app.get_windows();
                for (size_t i = 0; i < std::min(windows.size(), size_t(20)); ++i)
                {
                    std::wcout << L"  " << i << L": " << windows[i].title
                               << L" (" << windows[i].width() << L"x" << windows[i].height() << L")\n";
                }
                std::cout << std::endl;
            }
            break;
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    std::cout << "\n\nGoodbye!" << std::endl;
    return 0;
}
