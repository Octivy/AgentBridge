# AgentBridge SketchUp host adapter (Host Adapter Contract v1)
#
# SketchUp runs its own embedded Ruby. This file is dependency-free and serves
# the contract endpoints over a plain TCPServer on 127.0.0.1.
#
# SketchUp 2021+ bundles Ruby 3.x. Install: copy to
#   %APPDATA%\SketchUp\SketchUp <ver>\SketchUp\Plugins\cadcopilot_host.rb
#
# NOTE: this adapter is written to the full contract but has not been run
# inside SketchUp yet; verify on a machine with SketchUp installed.

require "json"
require "socket"
require "securerandom"
require "fileutils"

module AgentBridgeHost
  HOST_ID = "sketchup-main"
  HOST_KIND = "sketchup"
  PRODUCT = "SketchUp"
  PROTOCOL_VERSION = "1.0"

  TOOLS = [
    {
      "tool_name" => "sketchup_scene_summary",
      "display_name" => "场景摘要",
      "category" => "analysis",
      "description" => "汇总当前 SketchUp 模型中的实体数量、图层与文件名。",
      "input_schema" => {"type" => "object", "properties" => {}, "additionalProperties" => false},
      "dry_run_supported" => false,
      "side_effect_level" => "none",
      "result_schema" => {"type" => "object"}
    },
    {
      "tool_name" => "sketchup_create_box",
      "display_name" => "创建长方体",
      "category" => "modeling",
      "description" => "预览并创建一个长方体组对象，可回滚删除。",
      "input_schema" => {
        "type" => "object",
        "properties" => {
          "name" => {"type" => "string"},
          "size" => {"type" => "array", "items" => {"type" => "number"}, "minItems" => 3, "maxItems" => 3},
          "location" => {"type" => "array", "items" => {"type" => "number"}, "minItems" => 3, "maxItems" => 3}
        },
        "additionalProperties" => false
      },
      "dry_run_supported" => true,
      "side_effect_level" => "high",
      "result_schema" => {"type" => "object"},
      "rollback_supported" => true
    }
  ]

  ROLLBACK_LEDGER = {}

  def self.registry_dir
    base = ENV["LOCALAPPDATA"] || ENV["APPDATA"] || Dir.home
    File.join(base, "AgentBridge", "hosts")
  end

  def self.write_registration(port:, token:)
    dir = registry_dir
    FileUtils.mkdir_p(dir)
    registration = {
      "schema_version" => 1,
      "host_id" => HOST_ID,
      "host_kind" => HOST_KIND,
      "product" => PRODUCT,
      "product_version" => Sketchup.version,
      "protocol_version" => PROTOCOL_VERSION,
      "endpoint" => "http://127.0.0.1:#{port}",
      "token" => token,
      "pid" => Process.pid,
      "registered_at" => Time.now.utc.iso8601
    }
    path = File.join(dir, "#{HOST_ID}-#{Process.pid}.json")
    File.write(path, JSON.pretty_generate(registration))
  end

  def self.remove_registration
    Dir[File.join(registry_dir, "#{HOST_ID}-*.json")].each { |f| File.delete(f) }
  end

  def self.manifest
    {
      "schema_version" => 1,
      "host_id" => HOST_ID,
      "host_kind" => HOST_KIND,
      "product" => PRODUCT,
      "product_version" => Sketchup.version,
      "protocol_version" => PROTOCOL_VERSION,
      "capabilities" => ["snapshot", "dry_run", "rollback"],
      "tools" => TOOLS
    }
  end

  def self.health
    {
      "ok" => true,
      "product" => PRODUCT,
      "product_version" => Sketchup.version,
      "document_open" => !Sketchup.active_model.nil?,
      "detail" => {"host_id" => HOST_ID, "endpoint" => "http://127.0.0.1"}
    }
  end

  def self.snapshot(scope = {})
    model = Sketchup.active_model
    count = model ? model.entities.count : 0
    layers = model ? model.layers.map(&:name) : []
    {
      "ok" => true,
      "snapshot" => {
        "schema_version" => 1,
        "source" => "sketchup",
        "entity_count" => count,
        "model_name" => model && !model.path.to_s.empty? ? File.basename(model.path) : "",
        "layers" => layers
      }
    }
  end

  def self.execute(tool_name, arguments, dry_run)
    case tool_name
    when "sketchup_scene_summary"
      {"ok" => true, "result" => snapshot["snapshot"], "dry_run" => false}
    when "sketchup_create_box"
      create_box(arguments, dry_run)
    else
      {"ok" => false, "error_code" => "unknown_tool", "error_message" => "unknown tool: #{tool_name}"}
    end
  end

  def self.create_box(arguments, dry_run)
    size = (arguments["size"] || [2.0, 2.0, 2.0]).map { |v| v.to_f }
    location = (arguments["location"] || [0.0, 0.0, 0.0]).map { |v| v.to_f }
    name = (arguments["name"] || "AgentBridgeBox").to_s.strip
    preview = {"object_name" => name, "size" => size, "location" => location}
    return {"ok" => true, "result" => {"preview" => preview}, "dry_run" => true} if dry_run

    model = Sketchup.active_model
    raise "no active SketchUp model" if model.nil?

    entities = model.active_entities
    group = entities.add_group
    half = size.map { |v| v / 2.0 }
    points = [
      Geom::Point3d.new(location[0] - half[0], location[1] - half[1], location[2] - half[2]),
      Geom::Point3d.new(location[0] + half[0], location[1] - half[1], location[2] - half[2]),
      Geom::Point3d.new(location[0] + half[0], location[1] + half[1], location[2] - half[2]),
      Geom::Point3d.new(location[0] - half[0], location[1] + half[1], location[2] - half[2])
    ]
    face = group.entities.add_face(points)
    raise "failed to create face" if face.nil?
    face.pushpull(size[2])
    group.name = name
    token = "sketchup-box-#{name}"
    ROLLBACK_LEDGER[token] = {"kind" => "box", "name" => name}
    {
      "ok" => true,
      "result" => {"object_name" => name, "entity_count" => group.entities.count},
      "dry_run" => false,
      "rollback_token" => token
    }
  end

  def self.rollback(rollback_token)
    entry = ROLLBACK_LEDGER.delete(rollback_token)
    return {"ok" => false, "error_code" => "invalid_arguments", "error_message" => "unknown rollback token"} if entry.nil?

    model = Sketchup.active_model
    removed = 0
    if model
      model.active_entities.each do |entity|
        if entity.is_a?(Sketchup::Group) && entity.name == entry["name"]
          entity.erase!
          removed += 1
        end
      end
    end
    {"ok" => true, "result" => {"rolled_back" => true, "object_name" => entry["name"], "removed" => removed}}
  end

  def self.json_response(socket, status, payload)
    body = JSON.generate(payload)
    socket.write("HTTP/1.1 #{status} #{status == 200 ? "OK" : "Error"}\r\n")
    socket.write("Content-Type: application/json; charset=utf-8\r\n")
    socket.write("Content-Length: #{body.bytesize}\r\n")
    socket.write("Connection: close\r\n\r\n")
    socket.write(body)
  end

  def self.handle_connection(socket, token)
    request_line = socket.gets
    return if request_line.nil?

    method, path, = request_line.split(" ")
    headers = {}
    content_length = 0
    while (line = socket.gets)
      line = line.chomp
      break if line.empty?
      key, value = line.split(":", 2)
      headers[key.to_s.strip.downcase] = value.to_s.strip if key
    end
    body = ""
    if headers["content-length"]
      content_length = headers["content-length"].to_i
      body = socket.read(content_length) if content_length.positive?
    end

    unless headers["x-cadcopilot-token"] == token
      json_response(socket, 401, {"ok" => false, "error_code" => "unauthorized", "error_message" => "missing or invalid host token"})
      return
    end

    payload = begin
      body.empty? ? {} : JSON.parse(body)
    rescue JSON::ParserError
      {}
    end

    case [method, path.to_s.split("?").first]
    when ["GET", "/manifest"]
      json_response(socket, 200, manifest)
    when ["GET", "/health"]
      json_response(socket, 200, health)
    when ["POST", "/snapshot"]
      json_response(socket, 200, snapshot(payload["scope"] || {}))
    when ["POST", "/rollback"]
      json_response(socket, 200, rollback(payload["rollback_token"].to_s))
    else
      if method == "POST" && path.to_s.start_with?("/tools/")
        tool_name = path.to_s.split("/")[2]
        arguments = payload["arguments"] || {}
        dry_run = payload["dry_run"] == true
        tool = TOOLS.find { |item| item["tool_name"] == tool_name }
        if tool && tool["side_effect_level"] != "none" && !dry_run && arguments["permission_request_id"].to_s.empty?
          json_response(socket, 200, {
            "ok" => false,
            "error_code" => "permission_required",
            "error_message" => "write tools require a permission_request_id when dry_run is false"
          })
        else
          result = execute(tool_name, arguments, dry_run)
          result["dry_run"] = dry_run if result.is_a?(Hash)
          json_response(socket, 200, result)
        end
      else
        json_response(socket, 404, {"ok" => false, "error_code" => "not_found", "error_message" => "unknown endpoint"})
      end
    end
  rescue StandardError => exc
    json_response(socket, 200, {"ok" => false, "error_code" => "execution_error", "error_message" => exc.message})
  ensure
    socket.close rescue nil
  end

  def self.start(port: 0)
    token = SecureRandom.hex(32)
    server = TCPServer.new("127.0.0.1", port)
    actual_port = server.addr[1]
    write_registration(port: actual_port, token: token)
    puts "AGENTBRIDGE_SKETCHUP_HOST_READY http://127.0.0.1:#{actual_port} #{token}"
    loop do
      client = server.accept
      Thread.new(client, token) { |socket, t| handle_connection(socket, t) }
    end
  ensure
    server.close rescue nil
  end
end

# Auto-start the host when this file is loaded inside SketchUp (copy into
# %APPDATA%\SketchUp\SketchUp <ver>\SketchUp\Plugins\ and restart SketchUp).
# The host runs in a background thread so the SketchUp UI never blocks.
MARKER_DIR = File.join(ENV["LOCALAPPDATA"] || ENV["APPDATA"] || Dir.home, "AgentBridge")
begin
  FileUtils.mkdir_p(MARKER_DIR)
  File.write(File.join(MARKER_DIR, "sketchup-plugin-loaded.txt"), Time.now.utc.iso8601)
rescue StandardError
end

if defined?(Sketchup) && defined?(UI)
  Thread.new do
    begin
      AgentBridgeHost.start
    rescue StandardError => exc
      begin
        File.write(File.join(MARKER_DIR, "sketchup-host-error.txt"), exc.full_message)
      rescue StandardError
      end
    end
  end
end
