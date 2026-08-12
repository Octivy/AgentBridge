# AgentBridge SketchUp host adapter (skeleton, Host Adapter Contract v1)
#
# SketchUp runs its own embedded Ruby. This file should be loaded from a
# SketchUp extension (plugins/) and is intentionally dependency-free: it serves
# the contract endpoints over a plain TCPServer on 127.0.0.1.
#
# SketchUp 2021+ bundles Ruby 3.x. Install: copy to
#   %APPDATA%\SketchUp\SketchUp <ver>\SketchUp\Plugins\cadcopilot_host.rb

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
      "description" => "汇总当前 SketchUp 模型中的实体数量、图层与活动视图。",
      "input_schema" => {"type" => "object", "properties" => {}, "additionalProperties" => false},
      "dry_run_supported" => false,
      "side_effect_level" => "none",
      "result_schema" => {"type" => "object"}
    }
  ]

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

  def self.snapshot
    model = Sketchup.active_model
    entities = model ? model.entities.count : 0
    {
      "ok" => true,
      "snapshot" => {
        "schema_version" => 1,
        "source" => "sketchup",
        "entity_count" => entities,
        "model_name" => model ? File.basename(model.path) : "",
        "layers" => model ? model.layers.map(&:name) : []
      }
    }
  end

  # TODO: implement tools/execute and /rollback with SketchUp Ruby API,
  # mirroring adapters/blender/host.py. SketchUp main-thread calls must be
  # marshalled through Sketchup.set_status_text / UI.start_timer callbacks.
end
