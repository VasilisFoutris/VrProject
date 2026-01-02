/**
 * VR Streamer - Configuration Implementation
 * YAML configuration save/load.
 */

#include "core/config.hpp"
#include <fstream>
#include <sstream>

namespace vrs
{

    bool Config::save(const std::string &filepath) const
    {
        std::ofstream file(filepath);
        if (!file)
        {
            return false;
        }

        file << "# VR Streamer Configuration\n\n";

        file << "capture:\n"
             << "  target_fps: " << capture.target_fps << "\n"
             << "  monitor_index: " << capture.monitor_index << "\n"
             << "  capture_cursor: " << (capture.capture_cursor ? "true" : "false") << "\n"
             << "  use_gpu_capture: " << (capture.use_gpu_capture ? "true" : "false") << "\n"
             << "  frame_buffer_count: " << capture.frame_buffer_count << "\n"
             << "  wait_for_vsync: " << (capture.wait_for_vsync ? "true" : "false") << "\n"
             << "\n";

        file << "encoder:\n"
             << "  jpeg_quality: " << encoder.jpeg_quality << "\n"
             << "  downscale_factor: " << encoder.downscale_factor << "\n"
             << "  output_width: " << encoder.output_width << "\n"
             << "  output_height: " << encoder.output_height << "\n"
             << "  compression_method: ";

        switch (encoder.method)
        {
        case EncoderConfig::Method::JPEG:
            file << "jpeg";
            break;
        case EncoderConfig::Method::NVJPEG:
            file << "nvjpeg";
            break;
        case EncoderConfig::Method::TURBOJPEG:
            file << "turbojpeg";
            break;
        case EncoderConfig::Method::H264:
            file << "h264";
            break;
        case EncoderConfig::Method::RAW:
            file << "raw";
            break;
        }
        file << "\n";

        file << "  vr_enabled: " << (encoder.vr_enabled ? "true" : "false") << "\n"
             << "  eye_separation: " << encoder.eye_separation << "\n"
             << "  use_gpu: " << (encoder.use_gpu ? "true" : "false") << "\n"
             << "  gpu_device_id: " << encoder.gpu_device_id << "\n"
             << "  use_nvenc: " << (encoder.use_nvenc ? "true" : "false") << "\n"
             << "  use_nvjpeg: " << (encoder.use_nvjpeg ? "true" : "false") << "\n"
             << "  h264_bitrate: " << encoder.h264_bitrate << "\n"
             << "  h264_gop_length: " << encoder.h264_gop_length << "\n"
             << "  h264_low_latency: " << (encoder.h264_low_latency ? "true" : "false") << "\n"
             << "\n";

        file << "network:\n"
             << "  host: \"" << network.host << "\"\n"
             << "  port: " << network.port << "\n"
             << "  http_port: " << network.http_port << "\n"
             << "  static_ip: \"" << network.static_ip << "\"\n"
             << "  max_clients: " << network.max_clients << "\n"
             << "  send_buffer_size: " << network.send_buffer_size << "\n"
             << "  ping_interval: " << network.ping_interval << "\n"
             << "  use_tcp_nodelay: " << (network.use_tcp_nodelay ? "true" : "false") << "\n"
             << "  use_cork: " << (network.use_cork ? "true" : "false") << "\n";

        return file.good();
    }

    Config Config::load(const std::string &filepath)
    {
        Config config;

        std::ifstream file(filepath);
        if (!file)
        {
            return default_config();
        }

        // Simple YAML parser (for our specific format)
        std::string line;
        std::string section;

        auto parse_bool = [](const std::string &s) -> bool
        {
            return s == "true" || s == "yes" || s == "1";
        };

        auto parse_value = [](const std::string &line) -> std::string
        {
            size_t pos = line.find(':');
            if (pos == std::string::npos)
                return "";
            std::string value = line.substr(pos + 1);
            // Trim whitespace and quotes
            while (!value.empty() && (value.front() == ' ' || value.front() == '"'))
            {
                value.erase(0, 1);
            }
            while (!value.empty() && (value.back() == ' ' || value.back() == '"' || value.back() == '\r'))
            {
                value.pop_back();
            }
            return value;
        };

        while (std::getline(file, line))
        {
            // Skip comments and empty lines
            if (line.empty() || line[0] == '#')
                continue;

            // Check for section headers
            if (line[0] != ' ' && line.back() == ':')
            {
                section = line.substr(0, line.length() - 1);
                continue;
            }

            std::string value = parse_value(line);
            if (value.empty())
                continue;

            if (section == "capture")
            {
                if (line.find("target_fps:") != std::string::npos)
                {
                    config.capture.target_fps = std::stoi(value);
                }
                else if (line.find("monitor_index:") != std::string::npos)
                {
                    config.capture.monitor_index = std::stoi(value);
                }
                else if (line.find("capture_cursor:") != std::string::npos)
                {
                    config.capture.capture_cursor = parse_bool(value);
                }
                else if (line.find("use_gpu_capture:") != std::string::npos)
                {
                    config.capture.use_gpu_capture = parse_bool(value);
                }
                else if (line.find("frame_buffer_count:") != std::string::npos)
                {
                    config.capture.frame_buffer_count = std::stoi(value);
                }
                else if (line.find("wait_for_vsync:") != std::string::npos)
                {
                    config.capture.wait_for_vsync = parse_bool(value);
                }
            }
            else if (section == "encoder")
            {
                if (line.find("jpeg_quality:") != std::string::npos)
                {
                    config.encoder.jpeg_quality = std::stoi(value);
                }
                else if (line.find("downscale_factor:") != std::string::npos)
                {
                    config.encoder.downscale_factor = std::stof(value);
                }
                else if (line.find("output_width:") != std::string::npos)
                {
                    config.encoder.output_width = std::stoi(value);
                }
                else if (line.find("output_height:") != std::string::npos)
                {
                    config.encoder.output_height = std::stoi(value);
                }
                else if (line.find("compression_method:") != std::string::npos)
                {
                    if (value == "jpeg")
                        config.encoder.method = EncoderConfig::Method::JPEG;
                    else if (value == "nvjpeg")
                        config.encoder.method = EncoderConfig::Method::NVJPEG;
                    else if (value == "turbojpeg")
                        config.encoder.method = EncoderConfig::Method::TURBOJPEG;
                    else if (value == "h264")
                        config.encoder.method = EncoderConfig::Method::H264;
                    else if (value == "raw")
                        config.encoder.method = EncoderConfig::Method::RAW;
                }
                else if (line.find("vr_enabled:") != std::string::npos)
                {
                    config.encoder.vr_enabled = parse_bool(value);
                }
                else if (line.find("eye_separation:") != std::string::npos)
                {
                    config.encoder.eye_separation = std::stof(value);
                }
                else if (line.find("use_gpu:") != std::string::npos)
                {
                    config.encoder.use_gpu = parse_bool(value);
                }
                else if (line.find("gpu_device_id:") != std::string::npos)
                {
                    config.encoder.gpu_device_id = std::stoi(value);
                }
                else if (line.find("use_nvenc:") != std::string::npos)
                {
                    config.encoder.use_nvenc = parse_bool(value);
                }
                else if (line.find("use_nvjpeg:") != std::string::npos)
                {
                    config.encoder.use_nvjpeg = parse_bool(value);
                }
                else if (line.find("h264_bitrate:") != std::string::npos)
                {
                    config.encoder.h264_bitrate = std::stoi(value);
                }
                else if (line.find("h264_gop_length:") != std::string::npos)
                {
                    config.encoder.h264_gop_length = std::stoi(value);
                }
                else if (line.find("h264_low_latency:") != std::string::npos)
                {
                    config.encoder.h264_low_latency = parse_bool(value);
                }
            }
            else if (section == "network")
            {
                if (line.find("host:") != std::string::npos)
                {
                    config.network.host = value;
                }
                else if (line.find("http_port:") != std::string::npos)
                {
                    config.network.http_port = static_cast<u16>(std::stoi(value));
                }
                else if (line.find("port:") != std::string::npos)
                {
                    config.network.port = static_cast<u16>(std::stoi(value));
                }
                else if (line.find("static_ip:") != std::string::npos)
                {
                    config.network.static_ip = value;
                }
                else if (line.find("max_clients:") != std::string::npos)
                {
                    config.network.max_clients = std::stoi(value);
                }
                else if (line.find("send_buffer_size:") != std::string::npos)
                {
                    config.network.send_buffer_size = std::stoi(value);
                }
                else if (line.find("ping_interval:") != std::string::npos)
                {
                    config.network.ping_interval = std::stof(value);
                }
                else if (line.find("use_tcp_nodelay:") != std::string::npos)
                {
                    config.network.use_tcp_nodelay = parse_bool(value);
                }
                else if (line.find("use_cork:") != std::string::npos)
                {
                    config.network.use_cork = parse_bool(value);
                }
            }
        }

        return config;
    }

} // namespace vrs
